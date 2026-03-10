//! Bus message and topic constants (byte-compatible with Python).

use serde::{Deserialize, Serialize};

/// Schema version for bus messages; must match Python BUS_SCHEMA_VERSION.
pub const BUS_SCHEMA_VERSION: &str = "1.10";

/// Bus message envelope (JSON-compatible with Python BusMessage).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BusMessage {
    pub id: String,
    pub topic: String,
    pub payload: serde_json::Value,
    #[serde(default)]
    pub sender_id: String,
    #[serde(default)]
    pub timestamp: String,
    #[serde(default)]
    pub run_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub schema_version: Option<String>,
}

impl BusMessage {
    pub fn to_json(&self) -> crate::Result<String> {
        let mut obj = serde_json::to_value(self)?
            .as_object()
            .cloned()
            .unwrap_or_default();
        obj.insert(
            "schema_version".to_string(),
            serde_json::Value::String(BUS_SCHEMA_VERSION.to_string()),
        );
        Ok(serde_json::to_string(&serde_json::Value::Object(obj))?)
    }

    pub fn from_json(raw: &str) -> crate::Result<Self> {
        Ok(serde_json::from_str(raw)?)
    }
}

/// Payload as map for handlers that need dict-like access.
pub type BusMessagePayload = serde_json::Map<String, serde_json::Value>;

// Topic constants (must match hivemind/bus/topics.py)
pub mod topics {
    pub const TASK_READY: &str = "task.ready";
    pub const TASK_STARTED: &str = "task.started";
    pub const TASK_COMPLETED: &str = "task.completed";
    pub const TASK_FAILED: &str = "task.failed";
    pub const TASK_CLAIMED: &str = "task.claimed";
    pub const TASK_CLAIM_GRANTED: &str = "task.claim_granted";
    pub const TASK_CLAIM_REJECTED: &str = "task.claim_rejected";
    pub const AGENT_BROADCAST: &str = "agent.broadcast";
    pub const SWARM_CONTROL: &str = "swarm.control";
    pub const NODE_HEARTBEAT: &str = "node.heartbeat";
    pub const NODE_JOINED: &str = "node.joined";
    pub const NODE_LEFT: &str = "node.left";
    pub const NODE_BECAME_LEADER: &str = "node.became_leader";
    pub const NODE_LOST_LEADERSHIP: &str = "node.lost_leadership";
    pub const SWARM_SNAPSHOT: &str = "swarm.snapshot";
    pub const SWARM_STATUS_REQUEST: &str = "swarm.status_request";
    pub const SWARM_STATUS_RESPONSE: &str = "swarm.status_response";
}
