//! Controller node: dispatch loop, claim arbitration, snapshot, worker timeout.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use dashmap::DashMap;
use tokio::sync::RwLock;

use crate::bus::RedisBus;
use crate::election::LeaderElector;
use crate::error::Result;
use crate::registry::ClusterRegistry;
use crate::router::TaskRouter;
use crate::scheduler::Scheduler;
use crate::snapshot::SnapshotStore;
use crate::types::event::topics;
use crate::types::{AgentResponse, BusMessage, NodeInfo};

struct PendingClaim {
    dispatched_at: Instant,
    #[allow(dead_code)]
    target_worker: String,
    claimed: bool,
    worker_id: Option<String>,
}

/// Controller: leader election, dispatch loop, claim arbitration, snapshot, heartbeat monitor.
pub struct ControllerNode {
    pub node_id: String,
    pub run_id: String,
    bus: Arc<RwLock<RedisBus>>,
    registry: Arc<RwLock<ClusterRegistry>>,
    #[allow(dead_code)]
    elector: Arc<RwLock<LeaderElector>>,
    snapshot_store: Arc<RwLock<SnapshotStore>>,
    router: Arc<RwLock<TaskRouter>>,
    scheduler: Arc<RwLock<Option<Scheduler>>>,
    pending_claims: Arc<DashMap<String, PendingClaim>>,
    worker_stats: Arc<DashMap<String, serde_json::Value>>,
    claim_timeout_secs: u64,
    started_at: Instant,
}

impl ControllerNode {
    pub fn new(
        node_id: String,
        run_id: String,
        bus: Arc<RwLock<RedisBus>>,
        registry: Arc<RwLock<ClusterRegistry>>,
        elector: Arc<RwLock<LeaderElector>>,
        snapshot_store: Arc<RwLock<SnapshotStore>>,
        claim_timeout_secs: u64,
    ) -> Self {
        Self {
            node_id: node_id.clone(),
            run_id: run_id.clone(),
            bus,
            registry,
            elector,
            snapshot_store,
            router: Arc::new(RwLock::new(TaskRouter::new("1.10"))),
            scheduler: Arc::new(RwLock::new(None)),
            pending_claims: Arc::new(DashMap::new()),
            worker_stats: Arc::new(DashMap::new()),
            claim_timeout_secs,
            started_at: Instant::now(),
        }
    }

    /// Call with Arc<ControllerNode> so spawned tasks can hold a clone of the Arc.
    pub async fn become_leader(self: std::sync::Arc<Self>) -> Result<()> {
        let snapshot = {
            let mut store = self.snapshot_store.write().await;
            store.load(&self.run_id).await?
        };
        if let Some(snap) = snapshot {
            if let Some(sched) = Scheduler::restore(&snap) {
                let mut s = self.scheduler.write().await;
                *s = Some(sched);
                tracing::info!("Restored scheduler from snapshot");
            }
        }
        let node = self.clone();
        tokio::spawn(async move {
            if let Err(e) = node.dispatch_loop().await {
                tracing::warn!("dispatch_loop error: {:?}", e);
            }
        });
        let node = self.clone();
        tokio::spawn(async move {
            if let Err(e) = node.checkpoint_loop().await {
                tracing::warn!("checkpoint_loop error: {:?}", e);
            }
        });
        let node = self.clone();
        tokio::spawn(async move {
            if let Err(e) = node.worker_timeout_monitor().await {
                tracing::warn!("worker_timeout_monitor error: {:?}", e);
            }
        });
        self.publish_bus(
            topics::NODE_BECAME_LEADER,
            serde_json::json!({"node_id": self.node_id, "run_id": self.run_id}),
        )
        .await?;
        Ok(())
    }

    pub async fn lose_leadership(&self) -> Result<()> {
        self.publish_bus(
            topics::NODE_LOST_LEADERSHIP,
            serde_json::json!({"node_id": self.node_id}),
        )
        .await?;
        Ok(())
    }

    async fn publish_bus(&self, topic: &str, payload: serde_json::Value) -> Result<()> {
        let msg = BusMessage {
            id: uuid::Uuid::new_v4().to_string(),
            topic: topic.to_string(),
            payload,
            sender_id: self.node_id.clone(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            run_id: self.run_id.clone(),
            schema_version: None,
        };
        let mut bus = self.bus.write().await;
        bus.publish(&msg).await
    }

    async fn dispatch_loop(&self) -> Result<()> {
        loop {
            let sched_guard = self.scheduler.read().await;
            let sched = match sched_guard.as_ref() {
                Some(s) => s,
                None => {
                    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                    continue;
                }
            };
            if sched.is_finished() {
                break;
            }
            let ready = sched.get_ready_tasks();
            drop(sched_guard);

            let mut registry = self.registry.write().await;
            let workers = registry.get_workers().await?;
            drop(registry);

            let now = Instant::now();
            for task in ready {
                if self.pending_claims.contains_key(&task.id) {
                    let entry = self.pending_claims.get(&task.id);
                    if let Some(p) = entry {
                        if now.duration_since(p.dispatched_at).as_secs() > self.claim_timeout_secs {
                            self.pending_claims.remove(&task.id);
                        } else {
                            continue;
                        }
                    }
                }
                let workers_ref: Vec<NodeInfo> = workers.clone();
                let stats: HashMap<String, serde_json::Value> = self
                    .worker_stats
                    .iter()
                    .map(|r| (r.key().clone(), r.value().clone()))
                    .collect();
                let worker = {
                    let mut router = self.router.write().await;
                    router.route(&task, &workers_ref, &stats).cloned()
                };
                let worker = match worker {
                    Some(w) => w,
                    None => continue,
                };
                self.pending_claims.insert(
                    task.id.clone(),
                    PendingClaim {
                        dispatched_at: now,
                        target_worker: worker.node_id.clone(),
                        claimed: false,
                        worker_id: None,
                    },
                );
                let payload = serde_json::json!({
                    "id": task.id,
                    "description": task.description,
                    "dependencies": task.dependencies,
                    "status": task.status_value(),
                    "result": task.result,
                    "error": task.error,
                    "speculative": task.speculative,
                    "role": task.role,
                    "retry_count": task.retry_count,
                    "target_worker_id": worker.node_id,
                });
                let msg = BusMessage {
                    id: uuid::Uuid::new_v4().to_string(),
                    topic: topics::TASK_READY.to_string(),
                    payload,
                    sender_id: self.node_id.clone(),
                    timestamp: chrono::Utc::now().to_rfc3339(),
                    run_id: self.run_id.clone(),
                    schema_version: None,
                };
                self.bus.write().await.publish(&msg).await?;
            }
            tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;
        }
        Ok(())
    }

    async fn checkpoint_loop(&self) -> Result<()> {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(30)).await;
            let sched = self.scheduler.read().await;
            if let Some(s) = sched.as_ref() {
                let snapshot = s.snapshot();
                drop(sched);
                self.snapshot_store
                    .write()
                    .await
                    .save(&self.run_id, &snapshot)
                    .await?;
            }
        }
    }

    pub async fn on_task_claimed(&self, task_id: &str, worker_id: &str) -> Result<()> {
        let grant = if let Some(mut entry) = self.pending_claims.get_mut(task_id) {
            if entry.claimed {
                false
            } else {
                entry.claimed = true;
                entry.worker_id = Some(worker_id.to_string());
                true
            }
        } else {
            false
        };
        let topic = if grant {
            topics::TASK_CLAIM_GRANTED
        } else {
            topics::TASK_CLAIM_REJECTED
        };
        let payload = serde_json::json!({"task_id": task_id, "worker_id": worker_id});
        self.publish_bus(topic, payload).await
    }

    pub async fn on_task_completed(&self, response: &AgentResponse) -> Result<()> {
        {
            let mut sched = self.scheduler.write().await;
            if let Some(s) = sched.as_mut() {
                s.mark_completed(&response.task_id, &response.result);
            }
        }
        self.pending_claims.remove(&response.task_id);
        if let Some(snap) = self.scheduler.read().await.as_ref().map(|s| s.snapshot()) {
            self.snapshot_store
                .write()
                .await
                .save(&self.run_id, &snap)
                .await?;
        }
        Ok(())
    }

    pub async fn on_task_failed(&self, task_id: &str, error: &str) -> Result<()> {
        {
            let mut sched = self.scheduler.write().await;
            if let Some(s) = sched.as_mut() {
                s.mark_failed(task_id, error);
            }
        }
        self.pending_claims.remove(task_id);
        Ok(())
    }

    pub async fn on_heartbeat(&self, sender_id: &str, payload: serde_json::Value) -> Result<()> {
        let mut obj = payload.as_object().cloned().unwrap_or_default();
        obj.insert(
            "last_seen".to_string(),
            serde_json::Value::String(chrono::Utc::now().to_rfc3339()),
        );
        self.worker_stats
            .insert(sender_id.to_string(), serde_json::Value::Object(obj));
        let mut registry = self.registry.write().await;
        registry
            .heartbeat(
                sender_id,
                &serde_json::json!({"last_heartbeat": chrono::Utc::now().to_rfc3339()}),
            )
            .await?;
        Ok(())
    }

    async fn worker_timeout_monitor(&self) -> Result<()> {
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(10)).await;
            let now = chrono::Utc::now();
            let stale_workers: Vec<String> = self
                .worker_stats
                .iter()
                .filter_map(|r| {
                    let last = r.value().get("last_seen")?.as_str()?;
                    let t = chrono::DateTime::parse_from_rfc3339(last).ok()?;
                    if (now - t.with_timezone(&chrono::Utc)).num_seconds() > 30 {
                        Some(r.key().clone())
                    } else {
                        None
                    }
                })
                .collect();
            for worker_id in stale_workers {
                self.pending_claims
                    .retain(|_, p| p.worker_id.as_deref() != Some(worker_id.as_str()));
                self.worker_stats.remove(&worker_id);
                self.publish_bus(
                    topics::NODE_LEFT,
                    serde_json::json!({"node_id": worker_id, "lost_task_count": 0}),
                )
                .await?;
            }
        }
    }

    pub async fn get_status(&self) -> serde_json::Value {
        let (total, completed, failed, pending) = {
            let sched = self.scheduler.read().await;
            sched
                .as_ref()
                .map(|s| {
                    let tasks = s.get_all_tasks();
                    let total = tasks.len();
                    let completed = tasks
                        .iter()
                        .filter(|t| t.status == crate::types::TaskStatus::Completed)
                        .count();
                    let failed = tasks
                        .iter()
                        .filter(|t| t.status == crate::types::TaskStatus::Failed)
                        .count();
                    let pending = total - completed - failed;
                    (total, completed, failed, pending)
                })
                .unwrap_or((0, 0, 0, 0))
        };
        let workers: Vec<serde_json::Value> = self
            .registry
            .write()
            .await
            .get_workers()
            .await
            .ok()
            .unwrap_or_default()
            .into_iter()
            .map(|w| serde_json::to_value(&w).unwrap_or_default())
            .collect();
        let worker_stats: serde_json::Value = serde_json::Value::Object(
            self.worker_stats
                .iter()
                .map(|r| (r.key().clone(), r.value().clone()))
                .collect(),
        );
        serde_json::json!({
            "run_id": self.run_id,
            "node_id": self.node_id,
            "is_leader": true,
            "scheduler": { "total": total, "completed": completed, "failed": failed, "pending": pending },
            "workers": workers,
            "worker_stats": worker_stats,
            "uptime_seconds": self.started_at.elapsed().as_secs_f64(),
        })
    }

    pub async fn set_scheduler(&self, sched: Scheduler) {
        let mut s = self.scheduler.write().await;
        *s = Some(sched);
    }
}
