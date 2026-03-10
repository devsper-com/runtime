//! NodeInfo and NodeRole (compatible with Python cluster/node_info.py).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum NodeRole {
    Controller,
    Worker,
    Hybrid,
}

impl std::fmt::Display for NodeRole {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            NodeRole::Controller => write!(f, "controller"),
            NodeRole::Worker => write!(f, "worker"),
            NodeRole::Hybrid => write!(f, "hybrid"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeInfo {
    pub node_id: String,
    pub role: NodeRole,
    #[serde(default)]
    pub host: String,
    pub rpc_port: u16,
    #[serde(default)]
    pub rpc_url: String,
    #[serde(default)]
    pub tags: Vec<String>,
    pub max_workers: u32,
    #[serde(default)]
    pub joined_at: String,
    #[serde(default)]
    pub last_heartbeat: String,
    #[serde(default)]
    pub version: String,
}

impl NodeInfo {
    pub fn to_json(&self) -> crate::Result<String> {
        Ok(serde_json::to_string(self)?)
    }

    pub fn from_json(raw: &str) -> crate::Result<Self> {
        Ok(serde_json::from_str(raw)?)
    }
}
