use crate::types::{GraphMutation, GraphSnapshot, MemoryScope, NodeId, NodeSpec, RunId, RunState};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventEnvelope {
    pub event_id: String,
    pub run_id: RunId,
    pub sequence: u64,
    pub event: GraphEvent,
}

impl EventEnvelope {
    pub fn new(run_id: RunId, sequence: u64, event: GraphEvent) -> Self {
        Self {
            event_id: Uuid::new_v4().to_string(),
            run_id,
            sequence,
            event,
        }
    }

    pub fn ts(&self) -> u64 { self.event.ts() }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GraphEvent {
    RunStarted   { run_id: RunId, ts: u64 },
    RunCompleted { run_id: RunId, ts: u64 },
    RunFailed    { run_id: RunId, error: String, ts: u64 },
    RunStateChanged { run_id: RunId, from: RunState, to: RunState, ts: u64 },
    NodeAdded     { id: NodeId, spec: NodeSpec, ts: u64 },
    NodeReady     { id: NodeId, ts: u64 },
    NodeStarted   { id: NodeId, ts: u64 },
    NodeOutput    { id: NodeId, chunk: String, ts: u64 },
    NodeCompleted { id: NodeId, result: serde_json::Value, ts: u64 },
    NodeFailed    { id: NodeId, error: String, ts: u64 },
    NodeAbandoned { id: NodeId, ts: u64 },
    EdgeAdded   { from: NodeId, to: NodeId, ts: u64 },
    EdgeRemoved { from: NodeId, to: NodeId, ts: u64 },
    AgentStarted   { node_id: NodeId, model: String, ts: u64 },
    AgentCompleted { node_id: NodeId, input_tokens: u32, output_tokens: u32, ts: u64 },
    ToolCalled    { node_id: NodeId, tool_name: String, args: serde_json::Value, ts: u64 },
    ToolCompleted { node_id: NodeId, tool_name: String, duration_ms: u64, ts: u64 },
    ToolFailed    { node_id: NodeId, tool_name: String, error: String, ts: u64 },
    MemoryRead    { namespace: String, key: String, scope: MemoryScope, ts: u64 },
    MemoryWritten { namespace: String, key: String, scope: MemoryScope, ts: u64 },
    MutationApplied  { mutation: GraphMutation, ts: u64 },
    MutationRejected { reason: String, ts: u64 },
    SnapshotTaken    { snapshot: GraphSnapshot, ts: u64 },
    HitlRequested { node_id: NodeId, reason: String, ts: u64 },
    HitlApproved  { node_id: NodeId, ts: u64 },
    HitlRejected  { node_id: NodeId, reason: String, ts: u64 },
}

impl GraphEvent {
    pub fn ts(&self) -> u64 {
        match self {
            GraphEvent::RunStarted      { ts, .. } => *ts,
            GraphEvent::RunCompleted    { ts, .. } => *ts,
            GraphEvent::RunFailed       { ts, .. } => *ts,
            GraphEvent::RunStateChanged { ts, .. } => *ts,
            GraphEvent::NodeAdded       { ts, .. } => *ts,
            GraphEvent::NodeReady       { ts, .. } => *ts,
            GraphEvent::NodeStarted     { ts, .. } => *ts,
            GraphEvent::NodeOutput      { ts, .. } => *ts,
            GraphEvent::NodeCompleted   { ts, .. } => *ts,
            GraphEvent::NodeFailed      { ts, .. } => *ts,
            GraphEvent::NodeAbandoned   { ts, .. } => *ts,
            GraphEvent::EdgeAdded       { ts, .. } => *ts,
            GraphEvent::EdgeRemoved     { ts, .. } => *ts,
            GraphEvent::AgentStarted    { ts, .. } => *ts,
            GraphEvent::AgentCompleted  { ts, .. } => *ts,
            GraphEvent::ToolCalled      { ts, .. } => *ts,
            GraphEvent::ToolCompleted   { ts, .. } => *ts,
            GraphEvent::ToolFailed      { ts, .. } => *ts,
            GraphEvent::MemoryRead      { ts, .. } => *ts,
            GraphEvent::MemoryWritten   { ts, .. } => *ts,
            GraphEvent::MutationApplied  { ts, .. } => *ts,
            GraphEvent::MutationRejected { ts, .. } => *ts,
            GraphEvent::SnapshotTaken   { ts, .. } => *ts,
            GraphEvent::HitlRequested   { ts, .. } => *ts,
            GraphEvent::HitlApproved    { ts, .. } => *ts,
            GraphEvent::HitlRejected    { ts, .. } => *ts,
        }
    }
}

pub fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn envelope_roundtrip() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!({"ok": true}), ts: now_ms() },
        );
        let json = serde_json::to_string(&env).unwrap();
        let env2: EventEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(env2.run_id, run_id);
        assert_eq!(env2.sequence, 1);
        assert!(!env2.event_id.is_empty());
        assert!(env2.ts() > 0);
    }

    #[test]
    fn envelope_unique_event_ids() {
        let run_id = RunId::new();
        let e1 = EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
        let e2 = EventEnvelope::new(run_id.clone(), 1, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
        assert_ne!(e1.event_id, e2.event_id);
    }

    #[test]
    fn hitl_events_serialize() {
        let e = GraphEvent::HitlRequested { node_id: NodeId::new(), reason: "cost exceeded".to_string(), ts: now_ms() };
        let json = serde_json::to_string(&e).unwrap();
        let e2: GraphEvent = serde_json::from_str(&json).unwrap();
        assert!(e2.ts() > 0);
    }

    #[test]
    fn all_new_variants_roundtrip() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let ts = now_ms();
        let variants: Vec<GraphEvent> = vec![
            GraphEvent::AgentStarted { node_id: node_id.clone(), model: "m".to_string(), ts },
            GraphEvent::AgentCompleted { node_id: node_id.clone(), input_tokens: 10, output_tokens: 5, ts },
            GraphEvent::NodeOutput { id: node_id.clone(), chunk: "hello".to_string(), ts },
            GraphEvent::ToolCalled { node_id: node_id.clone(), tool_name: "t".to_string(), args: serde_json::json!({}), ts },
            GraphEvent::ToolCompleted { node_id: node_id.clone(), tool_name: "t".to_string(), duration_ms: 50, ts },
            GraphEvent::ToolFailed { node_id: node_id.clone(), tool_name: "t".to_string(), error: "e".to_string(), ts },
            GraphEvent::MemoryRead { namespace: "ns".to_string(), key: "k".to_string(), scope: MemoryScope::Run, ts },
            GraphEvent::MemoryWritten { namespace: "ns".to_string(), key: "k".to_string(), scope: MemoryScope::Context, ts },
            GraphEvent::HitlRequested { node_id: node_id.clone(), reason: "r".to_string(), ts },
            GraphEvent::HitlApproved { node_id: node_id.clone(), ts },
            GraphEvent::HitlRejected { node_id: node_id.clone(), reason: "r".to_string(), ts },
            GraphEvent::RunStateChanged { run_id: run_id.clone(), from: RunState::Created, to: RunState::Running, ts },
        ];
        for v in variants {
            let json = serde_json::to_string(&v).unwrap();
            let back: GraphEvent = serde_json::from_str(&json).unwrap();
            assert_eq!(back.ts(), ts);
        }
    }

    #[test]
    fn now_ms_is_reasonable() {
        assert!(now_ms() > 1_700_000_000_000);
    }
}
