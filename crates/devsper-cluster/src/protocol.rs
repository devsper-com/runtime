use devsper_core::{GraphEvent, GraphSnapshot, NodeId, RunId};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Messages exchanged between cluster peers
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClusterMessage {
    pub id: String,
    pub from: String,
    pub to: Option<String>,
    pub kind: ClusterMessageKind,
    pub ts: u64,
}

impl ClusterMessage {
    pub fn new(from: impl Into<String>, kind: ClusterMessageKind) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            from: from.into(),
            to: None,
            kind,
            ts: devsper_core::now_ms(),
        }
    }

    pub fn to_peer(mut self, peer_id: impl Into<String>) -> Self {
        self.to = Some(peer_id.into());
        self
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ClusterMessageKind {
    /// Peer announces itself to the cluster
    Hello {
        address: String,
        capabilities: Vec<String>,
    },

    /// Heartbeat (leader → all, worker → leader)
    Heartbeat { role: String },

    /// Leader election vote request
    VoteRequest { term: u64, candidate_id: String },

    /// Vote response
    VoteResponse { term: u64, granted: bool },

    /// Leader announces itself
    LeaderElected { leader_id: String, term: u64 },

    /// Task assignment (coordinator → worker)
    TaskAssign {
        run_id: RunId,
        node_id: NodeId,
        spec_json: String,
    },

    /// Task result (worker → coordinator)
    TaskResult {
        run_id: RunId,
        node_id: NodeId,
        result: serde_json::Value,
        mutations_json: Option<String>,
    },

    /// Task failure (worker → coordinator)
    TaskFailed {
        run_id: RunId,
        node_id: NodeId,
        error: String,
    },

    /// Graph event replication (coordinator → all peers)
    GraphEventReplication { run_id: RunId, event: GraphEvent },

    /// Snapshot sync (new peer or recovery)
    SnapshotSync {
        run_id: RunId,
        snapshot: GraphSnapshot,
    },
}
