//! Heartbeat loop — interval timer, payload assembly, publish.

use crate::types::event::topics;
use crate::types::BusMessage;

/// Payload for NODE_HEARTBEAT (matches Python worker heartbeat payload).
#[derive(serde::Serialize)]
pub struct HeartbeatPayload {
    pub node_id: String,
    pub active_tasks: u32,
    pub max_workers: u32,
    pub avg_task_duration_seconds: f64,
    pub load: f64,
    pub cached_tools: Vec<String>,
    pub completed_task_ids: Vec<String>,
    pub tags: Vec<String>,
    pub rpc_url: String,
}

pub fn make_heartbeat_message(
    payload: HeartbeatPayload,
    run_id: &str,
    sender_id: &str,
) -> BusMessage {
    BusMessage {
        id: uuid::Uuid::new_v4().to_string(),
        topic: topics::NODE_HEARTBEAT.to_string(),
        payload: serde_json::to_value(payload).unwrap_or_default(),
        sender_id: sender_id.to_string(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        run_id: run_id.to_string(),
        schema_version: None,
    }
}
