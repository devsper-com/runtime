use devsper_core::{now_ms, GraphSnapshot, Node, NodeId, RunId};
use std::collections::HashMap;

/// Build a snapshot from current graph state
pub fn build_snapshot(
    run_id: RunId,
    nodes: &HashMap<NodeId, Node>,
    edges: Vec<(NodeId, NodeId)>,
    event_count: u64,
) -> GraphSnapshot {
    GraphSnapshot {
        run_id,
        nodes: nodes.clone(),
        edges,
        event_count,
        snapshot_at: now_ms(),
    }
}
