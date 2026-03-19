//! Binary entrypoint: parse args, build runtime, start node.

use std::sync::Arc;

use clap::Parser;
use devsper_worker::bus::RedisBus;
use devsper_worker::config::NodeConfig;
use devsper_worker::registry::ClusterRegistry;
use devsper_worker::rpc;
use devsper_worker::types::event::topics;
use devsper_worker::types::{NodeInfo, NodeRole};
use devsper_worker::worker_node::WorkerNode;
use tracing::info;

#[derive(Parser, Debug)]
#[command(name = "devsper-worker")]
#[command(about = "devsper distributed worker node")]
struct Args {
    #[arg(long, env = "DEVSPER_NODE_ROLE", default_value = "worker")]
    role: String,
    #[arg(long, env = "DEVSPER_RPC_PORT", default_value = "7700")]
    port: u16,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let config = NodeConfig::from_env()?;
    let log_format = config.log_format.as_str();
    if log_format == "json" {
        tracing_subscriber::fmt()
            .json()
            .with_env_filter(tracing_subscriber::EnvFilter::new(&config.log_level))
            .init();
    } else {
        tracing_subscriber::fmt()
            .with_env_filter(tracing_subscriber::EnvFilter::new(&config.log_level))
            .init();
    }

    let _args = Args::parse();
    info!(node_id = %config.node_id, run_id = %config.run_id, worker_model = %config.worker_model, "starting worker node");

    let mut bus = RedisBus::new(config.redis_url.clone(), config.run_id.clone());
    let subscribe_topics: Vec<&str> = vec![
        topics::TASK_READY,
        topics::TASK_CLAIM_GRANTED,
        topics::TASK_CLAIM_REJECTED,
        topics::TOOL_RESULTS,
        topics::SWARM_SNAPSHOT,
        topics::SWARM_CONTROL,
    ];
    bus.start(&subscribe_topics).await?;

    let client = redis::Client::open(config.redis_url.as_str())
        .map_err(|e| format!("redis client: {}", e))?;
    let conn_registry = redis::aio::ConnectionManager::new(client)
        .await
        .map_err(|e| format!("redis connection: {}", e))?;
    let registry = ClusterRegistry::new(conn_registry, &config.run_id);

    // Bind RPC listener early so we can use the actual port (e.g. when config.rpc_port is 0) for registration.
    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", config.rpc_port)).await?;
    let effective_rpc_port = listener.local_addr()?.port();

    let host = hostname::get()
        .map(|h| h.into_string().unwrap_or_else(|_| "localhost".to_string()))
        .unwrap_or_else(|_| "localhost".to_string());
    let rpc_url = format!("http://{}:{}", host, effective_rpc_port);
    let node_info = NodeInfo {
        node_id: config.node_id.clone(),
        role: NodeRole::Worker,
        host: host.clone(),
        rpc_port: effective_rpc_port,
        rpc_url,
        tags: config.node_tags.clone(),
        max_workers: config.max_workers,
        joined_at: chrono::Utc::now().to_rfc3339(),
        last_heartbeat: chrono::Utc::now().to_rfc3339(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    };

    let bus = Arc::new(tokio::sync::RwLock::new(bus));
    let registry = Arc::new(tokio::sync::RwLock::new(registry));
    let worker = Arc::new(WorkerNode::new(
        config.clone(),
        node_info,
        bus.clone(),
        registry.clone(),
        config.run_id.clone(),
    ));
    worker.clone().start().await?;

    let mut rx = bus.write().await.subscribe();
    let worker_loop = worker.clone();
    tokio::spawn(async move {
        while let Ok(msg) = rx.recv().await {
            if msg.topic == topics::TASK_READY {
                let w = worker_loop.clone();
                tokio::spawn(async move {
                    let _ = w.handle_task_ready(&msg).await;
                });
            } else if msg.topic == topics::TASK_CLAIM_GRANTED {
                let task_id = msg
                    .payload
                    .get("task_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let worker_id = msg
                    .payload
                    .get("worker_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                worker_loop.on_claim_result(task_id, worker_id, true);
            } else if msg.topic == topics::TASK_CLAIM_REJECTED {
                let task_id = msg
                    .payload
                    .get("task_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let worker_id = msg
                    .payload
                    .get("worker_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                worker_loop.on_claim_result(task_id, worker_id, false);
            } else if msg.topic == topics::TOOL_RESULTS {
                let task_id = msg
                    .payload
                    .get("task_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let tool_results: Vec<serde_json::Value> = msg
                    .payload
                    .get("tool_results")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                worker_loop.on_tool_results(task_id, tool_results);
            } else if msg.topic == topics::SWARM_CONTROL {
                let w = worker_loop.clone();
                let payload = msg.payload.clone();
                tokio::spawn(async move {
                    let _ = w.on_control(&payload).await;
                });
            }
        }
    });
    let worker_heartbeat = worker.clone();
    tokio::spawn(async move {
        let _ = worker_heartbeat.heartbeat_loop().await;
    });

    let get_status = Arc::new(std::sync::Mutex::new(
        None::<
            Arc<
                dyn Fn() -> std::pin::Pin<
                        Box<dyn std::future::Future<Output = serde_json::Value> + Send>,
                    > + Send
                    + Sync,
            >,
        >,
    ));
    let get_current_tasks = Arc::new(move || worker.current_tasks_json());
    let rpc_state = Arc::new(rpc::RpcState {
        node_id: config.node_id.clone(),
        role: "worker".to_string(),
        started_at: std::time::Instant::now(),
        get_status,
        get_current_tasks,
        rpc_token: config.rpc_token.clone(),
    });

    let app = rpc::app(rpc_state);
    info!(port = effective_rpc_port, "RPC listening");
    axum::serve(listener, app).await?;
    Ok(())
}
