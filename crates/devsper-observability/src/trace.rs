use devsper_core::{NodeId, NodeStatus, RunId, RunState};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeTrace {
    pub node_id: NodeId,
    pub model: Option<String>,
    pub started_at: Option<u64>,
    pub completed_at: Option<u64>,
    pub latency_ms: Option<u64>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cost_usd: f64,
    pub status: NodeStatus,
    pub error: Option<String>,
}

impl NodeTrace {
    pub fn new(node_id: NodeId) -> Self {
        Self {
            node_id,
            model: None,
            started_at: None,
            completed_at: None,
            latency_ms: None,
            input_tokens: 0,
            output_tokens: 0,
            cost_usd: 0.0,
            status: NodeStatus::Pending,
            error: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunTrace {
    pub run_id: RunId,
    pub state: RunState,
    pub started_at: Option<u64>,
    pub completed_at: Option<u64>,
    pub total_latency_ms: Option<u64>,
    pub total_input_tokens: u32,
    pub total_output_tokens: u32,
    pub total_cost_usd: f64,
    pub nodes: HashMap<NodeId, NodeTrace>,
    pub event_count: u64,
}

impl RunTrace {
    pub fn new(run_id: RunId) -> Self {
        Self {
            run_id,
            state: RunState::Created,
            started_at: None,
            completed_at: None,
            total_latency_ms: None,
            total_input_tokens: 0,
            total_output_tokens: 0,
            total_cost_usd: 0.0,
            nodes: HashMap::new(),
            event_count: 0,
        }
    }
}
