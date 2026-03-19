//! Worker node: slot semaphore, task execution, claim protocol, heartbeat.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;

use dashmap::DashMap;
use tokio::sync::{oneshot, Semaphore};
use tracing::Instrument;

/// Type for tool results received from controller (TOOL_RESULTS payload array).
pub type ToolResultsPayload = Vec<serde_json::Value>;

use crate::bus::RedisBus;
use crate::claim::make_claim_message;
use crate::clarification;
use crate::config::{ExecutorMode, NodeConfig};
use crate::error::Result;
use crate::executor::{run_agent_pyo3, run_agent_subprocess};
use crate::heartbeat::{make_heartbeat_message, HeartbeatPayload};
use crate::metrics::Metrics;
use crate::registry::ClusterRegistry;
use crate::types::event::topics;
use crate::types::NodeInfo;
use crate::types::{AgentRequest, BusMessage, Task};

/// Worker node: subscribes to TASK_READY, claims, executes via executor, publishes results, heartbeats.
pub struct WorkerNode {
    pub config: NodeConfig,
    pub node_info: NodeInfo,
    pub run_id: String,
    bus: Arc<tokio::sync::RwLock<RedisBus>>,
    registry: Arc<tokio::sync::RwLock<ClusterRegistry>>,
    slots: Arc<Semaphore>,
    active_tasks: AtomicU32,
    task_durations: std::sync::Mutex<VecDeque<f64>>,
    last_completed_ids: std::sync::Mutex<VecDeque<String>>,
    pending_grants: Arc<DashMap<String, oneshot::Sender<bool>>>,
    /// When worker sends TASK_TOOL_CALLS it waits here for TOOL_RESULTS from controller.
    pending_tool_results: Arc<DashMap<String, oneshot::Sender<ToolResultsPayload>>>,
    paused: std::sync::atomic::AtomicBool,
    draining: std::sync::atomic::AtomicBool,
    metrics: Metrics,
}

impl WorkerNode {
    pub fn new(
        config: NodeConfig,
        node_info: NodeInfo,
        bus: Arc<tokio::sync::RwLock<RedisBus>>,
        registry: Arc<tokio::sync::RwLock<ClusterRegistry>>,
        run_id: String,
    ) -> Self {
        let max = config.max_workers as usize;
        Self {
            config,
            node_info: node_info.clone(),
            run_id: run_id.clone(),
            bus,
            registry,
            slots: Arc::new(Semaphore::new(max)),
            active_tasks: AtomicU32::new(0),
            task_durations: std::sync::Mutex::new(VecDeque::new()),
            last_completed_ids: std::sync::Mutex::new(VecDeque::new()),
            pending_grants: Arc::new(DashMap::new()),
            pending_tool_results: Arc::new(DashMap::new()),
            paused: std::sync::atomic::AtomicBool::new(false),
            draining: std::sync::atomic::AtomicBool::new(false),
            metrics: Metrics::default(),
        }
    }

    /// Called when TOOL_RESULTS message is received; unblocks the task waiting for tool results.
    pub fn on_tool_results(&self, task_id: &str, tool_results: ToolResultsPayload) {
        if let Some((_, tx)) = self.pending_tool_results.remove(task_id) {
            let _ = tx.send(tool_results);
        }
    }

    pub async fn start(&self) -> Result<()> {
        self.registry
            .write()
            .await
            .register(&self.node_info)
            .await?;
        self.publish_node_joined().await?;
        Ok(())
    }

    async fn publish_node_joined(&self) -> Result<()> {
        let payload =
            serde_json::to_value(&self.node_info).map_err(crate::error::DevsperError::Json)?;
        let msg = BusMessage {
            id: uuid::Uuid::new_v4().to_string(),
            topic: topics::NODE_JOINED.to_string(),
            payload,
            sender_id: self.node_info.node_id.clone(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            run_id: self.run_id.clone(),
            schema_version: None,
        };
        self.bus.write().await.publish(&msg).await
    }

    /// Call when a TASK_CLAIM_GRANTED or TASK_CLAIM_REJECTED message is received (from the bus loop).
    pub fn on_claim_result(&self, task_id: &str, worker_id: &str, granted: bool) {
        if worker_id != self.node_info.node_id {
            return;
        }
        if let Some((_, tx)) = self.pending_grants.remove(task_id) {
            let _ = tx.send(granted);
        }
    }

    pub async fn handle_task_ready(self: Arc<Self>, msg: &BusMessage) -> Result<()> {
        let payload =
            msg.payload
                .as_object()
                .ok_or(crate::error::DevsperError::InvalidPayload(
                    "no payload".to_string(),
                ))?;
        let target = payload.get("target_worker_id").and_then(|v| v.as_str());
        if let Some(tid) = target {
            if tid != self.node_info.node_id {
                return Ok(());
            }
        }
        if self.paused.load(Ordering::Relaxed) || self.draining.load(Ordering::Relaxed) {
            return Ok(());
        }
        let permit = match self.slots.clone().try_acquire_owned() {
            Ok(p) => p,
            Err(_) => return Ok(()),
        };
        let task: Task = serde_json::from_value(serde_json::Value::Object(payload.clone()))
            .map_err(|e| crate::error::DevsperError::InvalidPayload(e.to_string()))?;
        let task_id_short = task.id.chars().take(12).collect::<String>();
        tracing::info!(worker = %self.node_info.node_id[..8.min(self.node_info.node_id.len())], task = %task_id_short, "received TASK_READY");
        let claim_msg = make_claim_message(
            &task.id,
            &self.node_info.node_id,
            &self.run_id,
            &self.node_info.node_id,
        );
        self.bus.write().await.publish(&claim_msg).await?;
        let (grant_tx, grant_rx) = oneshot::channel();
        self.pending_grants.insert(task.id.clone(), grant_tx);
        let timeout = tokio::time::Duration::from_secs(self.config.claim_timeout_secs);
        let granted = tokio::select! {
            _ = tokio::time::sleep(timeout) => {
                self.pending_grants.remove(&task.id);
                tracing::warn!("claim timeout for task {}", task_id_short);
                false
            }
            r = grant_rx => r.unwrap_or(false)
        };
        if !granted {
            drop(permit);
            return Ok(());
        }
        self.active_tasks.fetch_add(1, Ordering::Relaxed);
        let task_id_span = task.id.clone();
        let node = self.clone();
        tokio::spawn(
            async move {
                let _permit = permit;
                if let Err(e) = node.execute_task(task).await {
                    tracing::warn!("execute_task error: {:?}", e);
                }
            }
            .instrument(tracing::info_span!("execute", task = %task_id_span)),
        );
        Ok(())
    }

    async fn execute_task(self: Arc<Self>, task: Task) -> Result<()> {
        let start = tokio::time::Instant::now();
        let task_id_short = task.id.chars().take(12).collect::<String>();
        let tool_names = task.tools.clone().unwrap_or_default();
        let use_distributed_tools = !tool_names.is_empty();
        let mut request = AgentRequest {
            task: task.clone(),
            memory_context: String::new(),
            tools: tool_names,
            model: self.config.worker_model.clone(),
            system_prompt: String::new(),
            prefetch_used: false,
            tool_results: None,
            distributed_tools: use_distributed_tools,
        };
        let timeout_secs = Some(300u64);
        let response = loop {
            let resp = match self.config.executor_mode {
                ExecutorMode::Subprocess => {
                    run_agent_subprocess(&self.config.python_bin, &request, timeout_secs).await
                }
                ExecutorMode::PyO3 => run_agent_pyo3(&request, timeout_secs).await,
            };
            let resp = match resp {
                Ok(r) => r,
                Err(e) => {
                    self.bus
                        .write()
                        .await
                        .publish(&self.make_task_failed(&task.id, &e.to_string()))
                        .await?;
                    self.active_tasks.fetch_sub(1, Ordering::Relaxed);
                    self.metrics.inc_failed();
                    return Err(e);
                }
            };
            let tool_calls = resp.tool_calls.as_ref().filter(|c| !c.is_empty());
            if tool_calls.is_none() {
                break resp;
            }
            let tool_calls = tool_calls.unwrap();
            let payload = serde_json::json!({
                "task_id": task.id,
                "worker_id": self.node_info.node_id,
                "tool_calls": tool_calls,
            });
            let msg = BusMessage {
                id: uuid::Uuid::new_v4().to_string(),
                topic: topics::TASK_TOOL_CALLS.to_string(),
                payload,
                sender_id: self.node_info.node_id.clone(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                run_id: self.run_id.clone(),
                schema_version: None,
            };
            self.bus.write().await.publish(&msg).await?;
            let (tx, rx) = oneshot::channel();
            self.pending_tool_results
                .insert(task.id.clone(), tx);
            let tool_results = match tokio::time::timeout(
                tokio::time::Duration::from_secs(120),
                rx,
            )
            .await
            {
                Ok(Ok(tr)) => tr,
                Ok(Err(_)) => {
                    self.pending_tool_results.remove(&task.id);
                    self.bus
                        .write()
                        .await
                        .publish(&self.make_task_failed(
                            &task.id,
                            "tool results channel closed",
                        ))
                        .await?;
                    self.active_tasks.fetch_sub(1, Ordering::Relaxed);
                    self.metrics.inc_failed();
                    return Err(crate::error::DevsperError::InvalidPayload(
                        "tool results channel closed".to_string(),
                    ));
                }
                Err(_) => {
                    self.pending_tool_results.remove(&task.id);
                    self.bus
                        .write()
                        .await
                        .publish(&self.make_task_failed(
                            &task.id,
                            "timeout waiting for TOOL_RESULTS",
                        ))
                        .await?;
                    self.active_tasks.fetch_sub(1, Ordering::Relaxed);
                    self.metrics.inc_failed();
                    return Err(crate::error::DevsperError::InvalidPayload(
                        "timeout waiting for TOOL_RESULTS".to_string(),
                    ));
                }
            };
            request.tool_results = Some(tool_results);
            request.distributed_tools = true;
        };
        let mut response = response;
        if clarification::is_clarification_response(&response.result) {
            let request_id = uuid::Uuid::new_v4().to_string();
            let timeout_secs = 120u64;
            if let Some(req_payload) = clarification::build_request_payload(
                &request_id,
                &task.id,
                "agent",
                &response.result,
                timeout_secs,
            ) {
                let channel_req = format!("{}.{}", topics::CLARIFICATION_REQUEST_TOPIC, self.run_id);
                let msg_req = BusMessage {
                    id: uuid::Uuid::new_v4().to_string(),
                    topic: channel_req.clone(),
                    payload: serde_json::json!({
                        "request": req_payload,
                        "node_id": self.node_info.node_id
                    }),
                    sender_id: self.node_info.node_id.clone(),
                    timestamp: chrono::Utc::now().to_rfc3339(),
                    run_id: self.run_id.clone(),
                    schema_version: None,
                };
                self.bus.write().await.publish_to_channel(&channel_req, &msg_req).await?;
                // Must match Python RedisBus._channel(topic, run_id) => "{topic}:{run_id}"
                let response_channel = format!(
                    "{}.{}.{}:{}",
                    topics::CLARIFICATION_RESPONSE_TOPIC,
                    self.run_id,
                    request_id,
                    self.run_id
                );
                let payload_opt = RedisBus::recv_once_on_channel(
                    &self.config.redis_url,
                    &response_channel,
                    timeout_secs,
                )
                .await?;
                let (append_desc, re_run) = match payload_opt
                    .as_ref()
                    .and_then(clarification::parse_clarification_response)
                {
                    Some(parsed) if parsed.skipped || parsed.answers.is_empty() => (
                        "\n\n[Proceed without user clarification; use available information to complete the task.]".to_string(),
                        true,
                    ),
                    Some(parsed) => (
                        clarification::format_clarification_context(&parsed.answers),
                        true,
                    ),
                    None => (
                        "\n\n[Proceed without user clarification; use available information to complete the task.]".to_string(),
                        true,
                    ),
                };
                if re_run {
                    request.task.description = request.task.description + &append_desc;
                    let resp2 = match self.config.executor_mode {
                        ExecutorMode::Subprocess => {
                            run_agent_subprocess(&self.config.python_bin, &request, Some(300)).await
                        }
                        ExecutorMode::PyO3 => run_agent_pyo3(&request, Some(300)).await,
                    };
                    if let Ok(r) = resp2 {
                        response = r;
                    }
                }
            }
        }
        let elapsed = start.elapsed().as_secs_f64();
        {
            let mut d = self.task_durations.lock().unwrap();
            d.push_back(elapsed);
            if d.len() > 10 {
                d.pop_front();
            }
        }
        {
            let mut c = self.last_completed_ids.lock().unwrap();
            c.push_back(task.id.clone());
            if c.len() > 50 {
                c.pop_front();
            }
        }
        self.metrics.inc_completed();
        self.active_tasks.fetch_sub(1, Ordering::Relaxed);
        let result_len = response.result.len();
        tracing::info!(worker = %self.node_info.node_id[..8.min(self.node_info.node_id.len())], task = %task_id_short, elapsed = %elapsed, result_len = result_len, "task completed");
        if result_len == 0 {
            tracing::warn!(task = %task_id_short, error = ?response.error, "agent returned empty result");
        }
        let msg = BusMessage {
            id: uuid::Uuid::new_v4().to_string(),
            topic: topics::TASK_COMPLETED.to_string(),
            payload: serde_json::to_value(&response).map_err(crate::error::DevsperError::Json)?,
            sender_id: self.node_info.node_id.clone(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            run_id: self.run_id.clone(),
            schema_version: None,
        };
        self.bus.write().await.publish(&msg).await
    }

    fn make_task_failed(&self, task_id: &str, error: &str) -> BusMessage {
        BusMessage {
            id: uuid::Uuid::new_v4().to_string(),
            topic: topics::TASK_FAILED.to_string(),
            payload: serde_json::json!({
                "task_id": task_id,
                "error": error,
                "error_type": "Error",
                "worker_id": self.node_info.node_id,
            }),
            sender_id: self.node_info.node_id.clone(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            run_id: self.run_id.clone(),
            schema_version: None,
        }
    }

    pub async fn heartbeat_loop(&self) -> Result<()> {
        let interval = tokio::time::Duration::from_secs(self.config.heartbeat_interval_secs);
        loop {
            tokio::time::sleep(interval).await;
            if self.paused.load(Ordering::Relaxed) {
                continue;
            }
            let active = self.active_tasks.load(Ordering::Relaxed);
            let avg: f64 = {
                let d = self.task_durations.lock().unwrap();
                if d.is_empty() {
                    0.0
                } else {
                    d.iter().sum::<f64>() / d.len() as f64
                }
            };
            let completed: Vec<String> = self
                .last_completed_ids
                .lock()
                .unwrap()
                .iter()
                .cloned()
                .rev()
                .take(50)
                .collect();
            let payload = HeartbeatPayload {
                node_id: self.node_info.node_id.clone(),
                active_tasks: active,
                max_workers: self.node_info.max_workers,
                avg_task_duration_seconds: avg,
                load: active as f64 / self.node_info.max_workers as f64,
                cached_tools: vec![],
                completed_task_ids: completed,
                tags: self.node_info.tags.clone(),
                rpc_url: self.node_info.rpc_url.clone(),
            };
            let msg = make_heartbeat_message(payload, &self.run_id, &self.node_info.node_id);
            self.bus.write().await.publish(&msg).await?;
            self.registry
                .write()
                .await
                .heartbeat(
                    &self.node_info.node_id,
                    &serde_json::json!({"last_heartbeat": chrono::Utc::now().to_rfc3339()}),
                )
                .await?;
        }
    }

    pub async fn on_control(&self, payload: &serde_json::Value) -> Result<()> {
        let command = payload.get("command").and_then(|v| v.as_str());
        let target = payload
            .get("target")
            .and_then(|v| v.as_str())
            .unwrap_or("all");
        if target != "all" && target != self.node_info.node_id {
            return Ok(());
        }
        match command {
            Some("pause") => self.paused.store(true, Ordering::Relaxed),
            Some("resume") => self.paused.store(false, Ordering::Relaxed),
            Some("drain") => self.draining.store(true, Ordering::Relaxed),
            _ => {}
        }
        Ok(())
    }

    pub fn current_tasks_json(&self) -> Vec<serde_json::Value> {
        vec![]
    }
}
