use crate::types::{GraphMutation, GraphSnapshot, NodeId, NodeSpec, RunId};
use serde::{Deserialize, Serialize};

/// All events that can occur in a graph's lifecycle
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GraphEvent {
    NodeAdded {
        id: NodeId,
        spec: NodeSpec,
        ts: u64,
    },
    NodeReady {
        id: NodeId,
        ts: u64,
    },
    NodeStarted {
        id: NodeId,
        ts: u64,
    },
    NodeCompleted {
        id: NodeId,
        result: serde_json::Value,
        ts: u64,
    },
    NodeFailed {
        id: NodeId,
        error: String,
        ts: u64,
    },
    NodeAbandoned {
        id: NodeId,
        ts: u64,
    },
    EdgeAdded {
        from: NodeId,
        to: NodeId,
        ts: u64,
    },
    EdgeRemoved {
        from: NodeId,
        to: NodeId,
        ts: u64,
    },
    MutationApplied {
        mutation: GraphMutation,
        ts: u64,
    },
    MutationRejected {
        reason: String,
        ts: u64,
    },
    SnapshotTaken {
        snapshot: GraphSnapshot,
        ts: u64,
    },
    RunStarted {
        run_id: RunId,
        ts: u64,
    },
    RunCompleted {
        run_id: RunId,
        ts: u64,
    },
    RunFailed {
        run_id: RunId,
        error: String,
        ts: u64,
    },
}

impl GraphEvent {
    pub fn ts(&self) -> u64 {
        match self {
            GraphEvent::NodeAdded { ts, .. } => *ts,
            GraphEvent::NodeReady { ts, .. } => *ts,
            GraphEvent::NodeStarted { ts, .. } => *ts,
            GraphEvent::NodeCompleted { ts, .. } => *ts,
            GraphEvent::NodeFailed { ts, .. } => *ts,
            GraphEvent::NodeAbandoned { ts, .. } => *ts,
            GraphEvent::EdgeAdded { ts, .. } => *ts,
            GraphEvent::EdgeRemoved { ts, .. } => *ts,
            GraphEvent::MutationApplied { ts, .. } => *ts,
            GraphEvent::MutationRejected { ts, .. } => *ts,
            GraphEvent::SnapshotTaken { ts, .. } => *ts,
            GraphEvent::RunStarted { ts, .. } => *ts,
            GraphEvent::RunCompleted { ts, .. } => *ts,
            GraphEvent::RunFailed { ts, .. } => *ts,
        }
    }
}

/// Helper to get current timestamp in milliseconds
pub fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::NodeId;

    #[test]
    fn graph_event_serializes() {
        let id = NodeId::new();
        let event = GraphEvent::NodeCompleted {
            id: id.clone(),
            result: serde_json::json!({"output": "done"}),
            ts: now_ms(),
        };
        let json = serde_json::to_string(&event).unwrap();
        let event2: GraphEvent = serde_json::from_str(&json).unwrap();
        assert!(event2.ts() > 0);
    }

    #[test]
    fn now_ms_is_reasonable() {
        let ts = now_ms();
        assert!(ts > 1_700_000_000_000); // after 2023
    }
}
