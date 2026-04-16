use serde::{Deserialize, Serialize};

/// Information about a known cluster peer
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeerInfo {
    pub id: String,
    pub address: String,
    pub role: String,
    pub last_seen_ms: u64,
    pub capabilities: Vec<String>,
}

impl PeerInfo {
    pub fn new(id: impl Into<String>, address: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            address: address.into(),
            role: "worker".to_string(),
            last_seen_ms: devsper_core::now_ms(),
            capabilities: vec![],
        }
    }

    pub fn is_alive(&self, timeout_ms: u64) -> bool {
        devsper_core::now_ms() - self.last_seen_ms < timeout_ms
    }
}
