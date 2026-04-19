use devsper_core::{
    EventEnvelope, GraphEvent, Node, NodeId, NodeStatus, RunState,
};
use std::collections::HashMap;

#[derive(Debug, Clone, Default)]
pub struct ReplayState {
    pub nodes: HashMap<NodeId, Node>,
    pub edges: Vec<(NodeId, NodeId)>,
    pub run_state: RunState,
    pub event_count: u64,
}

/// Reconstruct full run state from an ordered event log.
/// Sorts by sequence before applying — guarantees determinism regardless of input order.
pub fn replay(envelopes: &[EventEnvelope]) -> ReplayState {
    let mut state = ReplayState::default();
    let mut sorted: Vec<&EventEnvelope> = envelopes.iter().collect();
    sorted.sort_by_key(|e| e.sequence);

    for envelope in sorted {
        state.event_count += 1;
        apply(&mut state, &envelope.event);
    }
    state
}

fn apply(state: &mut ReplayState, event: &GraphEvent) {
    match event {
        GraphEvent::RunStarted { .. } => {
            state.run_state = RunState::Running;
        }
        GraphEvent::RunCompleted { .. } => {
            state.run_state = RunState::Completed;
        }
        GraphEvent::RunFailed { .. } => {
            state.run_state = RunState::Failed;
        }
        GraphEvent::RunStateChanged { to, .. } => {
            state.run_state = to.clone();
        }
        GraphEvent::NodeAdded { id, spec, .. } => {
            state.nodes.entry(id.clone()).or_insert_with(|| Node::new(spec.clone()));
        }
        GraphEvent::EdgeAdded { from, to, .. } => {
            if !state.edges.contains(&(from.clone(), to.clone())) {
                state.edges.push((from.clone(), to.clone()));
            }
        }
        GraphEvent::EdgeRemoved { from, to, .. } => {
            state.edges.retain(|(f, t)| f != from || t != to);
        }
        GraphEvent::NodeReady { id, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Ready;
            }
        }
        GraphEvent::NodeStarted { id, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Running;
                node.started_at = Some(*ts);
            }
        }
        GraphEvent::NodeCompleted { id, result, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Completed;
                node.result = Some(result.clone());
                node.completed_at = Some(*ts);
            }
        }
        GraphEvent::NodeFailed { id, error, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Failed;
                node.error = Some(error.clone());
                node.completed_at = Some(*ts);
            }
        }
        GraphEvent::NodeAbandoned { id, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Abandoned;
            }
        }
        GraphEvent::HitlRequested { .. } => {
            state.run_state = RunState::WaitingHITL;
        }
        GraphEvent::HitlApproved { .. } => {
            state.run_state = RunState::Running;
        }
        GraphEvent::HitlRejected { .. } => {
            state.run_state = RunState::Failed;
        }
        // NodeOutput, AgentStarted/Completed, ToolCalled/Completed/Failed,
        // MemoryRead/Written, MutationApplied/Rejected, SnapshotTaken — no state change
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{EventEnvelope, GraphEvent, NodeSpec, RunId, now_ms};

    fn make_run(run_id: &RunId, seq: u64, event: GraphEvent) -> EventEnvelope {
        EventEnvelope::new(run_id.clone(), seq, event)
    }

    #[test]
    fn empty_produces_created_state() {
        let state = replay(&[]);
        assert_eq!(state.run_state, RunState::Created);
        assert_eq!(state.event_count, 0);
    }

    #[test]
    fn run_start_then_complete() {
        let run_id = RunId::new();
        let ts = now_ms();
        let events = vec![
            make_run(&run_id, 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            make_run(&run_id, 1, GraphEvent::RunCompleted { run_id: run_id.clone(), ts }),
        ];
        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
        assert_eq!(state.event_count, 2);
    }

    #[test]
    fn node_lifecycle_reconstructed() {
        let run_id = RunId::new();
        let spec = NodeSpec::new("task-a");
        let node_id = spec.id.clone();
        let ts = now_ms();
        let events = vec![
            make_run(&run_id, 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            make_run(&run_id, 1, GraphEvent::NodeAdded { id: node_id.clone(), spec: spec.clone(), ts }),
            make_run(&run_id, 2, GraphEvent::NodeStarted { id: node_id.clone(), ts: ts + 10 }),
            make_run(&run_id, 3, GraphEvent::NodeCompleted {
                id: node_id.clone(), result: serde_json::json!({"out": "done"}), ts: ts + 100
            }),
            make_run(&run_id, 4, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 110 }),
        ];
        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
        let node = state.nodes.get(&node_id).unwrap();
        assert_eq!(node.status, NodeStatus::Completed);
        assert_eq!(node.result.as_ref().unwrap()["out"], "done");
    }

    #[test]
    fn deterministic_regardless_of_input_order() {
        let run_id = RunId::new();
        let spec = NodeSpec::new("task");
        let node_id = spec.id.clone();
        let ts = now_ms();
        let mut events = vec![
            make_run(&run_id, 2, GraphEvent::NodeCompleted {
                id: node_id.clone(), result: serde_json::json!({"x": 1}), ts: ts + 50
            }),
            make_run(&run_id, 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            make_run(&run_id, 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
            make_run(&run_id, 3, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 60 }),
        ];
        let state1 = replay(&events);
        events.reverse();
        let state2 = replay(&events);
        assert_eq!(state1.run_state, state2.run_state);
        assert_eq!(state1.nodes[&node_id].status, state2.nodes[&node_id].status);
        assert_eq!(state1.event_count, state2.event_count);
    }

    #[test]
    fn hitl_pause_and_resume() {
        let run_id = RunId::new();
        let spec = NodeSpec::new("hitl-task");
        let node_id = spec.id.clone();
        let ts = now_ms();
        let events = vec![
            make_run(&run_id, 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            make_run(&run_id, 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
            make_run(&run_id, 2, GraphEvent::HitlRequested { node_id: node_id.clone(), reason: "cost".to_string(), ts }),
            make_run(&run_id, 3, GraphEvent::HitlApproved { node_id: node_id.clone(), ts: ts + 1000 }),
            make_run(&run_id, 4, GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts: ts + 2000 }),
            make_run(&run_id, 5, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 2010 }),
        ];
        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
    }

    #[test]
    fn replay_is_idempotent() {
        let run_id = RunId::new();
        let spec = NodeSpec::new("task");
        let node_id = spec.id.clone();
        let ts = now_ms();
        let events = vec![
            make_run(&run_id, 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            make_run(&run_id, 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
            make_run(&run_id, 2, GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts }),
            make_run(&run_id, 3, GraphEvent::RunCompleted { run_id: run_id.clone(), ts }),
        ];
        let s1 = replay(&events);
        let s2 = replay(&events);
        assert_eq!(s1.run_state, s2.run_state);
        assert_eq!(s1.nodes[&node_id].status, s2.nodes[&node_id].status);
        assert_eq!(s1.event_count, s2.event_count);
    }
}
