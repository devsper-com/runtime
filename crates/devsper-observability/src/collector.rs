use crate::trace::{NodeTrace, RunTrace};
use devsper_core::{EventEnvelope, GraphEvent, NodeStatus, RunId, RunState};
use std::sync::Arc;
use tokio::sync::RwLock;

pub struct TraceCollector {
    inner: Arc<RwLock<RunTrace>>,
}

impl TraceCollector {
    pub fn new(run_id: RunId) -> Self {
        Self { inner: Arc::new(RwLock::new(RunTrace::new(run_id))) }
    }

    pub async fn ingest(&self, envelope: &EventEnvelope) {
        let mut trace = self.inner.write().await;
        trace.event_count += 1;

        match &envelope.event {
            GraphEvent::RunStarted { ts, .. } => {
                trace.state = RunState::Running;
                trace.started_at = Some(*ts);
            }
            GraphEvent::RunCompleted { ts, .. } => {
                trace.state = RunState::Completed;
                trace.completed_at = Some(*ts);
                if let (Some(start), Some(end)) = (trace.started_at, trace.completed_at) {
                    trace.total_latency_ms = Some(end.saturating_sub(start));
                }
            }
            GraphEvent::RunFailed { ts, .. } => {
                trace.state = RunState::Failed;
                trace.completed_at = Some(*ts);
                if let (Some(start), Some(end)) = (trace.started_at, trace.completed_at) {
                    trace.total_latency_ms = Some(end.saturating_sub(start));
                }
            }
            GraphEvent::RunStateChanged { to, .. } => {
                trace.state = to.clone();
            }
            GraphEvent::NodeStarted { id, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.started_at = Some(*ts);
                node.status = NodeStatus::Running;
            }
            GraphEvent::NodeCompleted { id, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.completed_at = Some(*ts);
                node.status = NodeStatus::Completed;
                if let Some(start) = node.started_at {
                    node.latency_ms = Some(ts.saturating_sub(start));
                }
            }
            GraphEvent::NodeFailed { id, error, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.completed_at = Some(*ts);
                node.status = NodeStatus::Failed;
                node.error = Some(error.clone());
                if let Some(start) = node.started_at {
                    node.latency_ms = Some(ts.saturating_sub(start));
                }
            }
            GraphEvent::AgentStarted { node_id, model, .. } => {
                let node = trace.nodes.entry(node_id.clone()).or_insert_with(|| NodeTrace::new(node_id.clone()));
                node.model = Some(model.clone());
            }
            GraphEvent::AgentCompleted { node_id, input_tokens, output_tokens, .. } => {
                // Rough cost: $3/1M input, $15/1M output (Sonnet pricing)
                let cost_usd = (*input_tokens as f64 / 1_000_000.0) * 3.0
                    + (*output_tokens as f64 / 1_000_000.0) * 15.0;
                {
                    let node = trace.nodes.entry(node_id.clone()).or_insert_with(|| NodeTrace::new(node_id.clone()));
                    node.input_tokens = *input_tokens;
                    node.output_tokens = *output_tokens;
                    node.cost_usd = cost_usd;
                }
                trace.total_input_tokens += input_tokens;
                trace.total_output_tokens += output_tokens;
                trace.total_cost_usd += cost_usd;
            }
            _ => {}
        }
    }

    pub async fn snapshot(&self) -> RunTrace {
        self.inner.read().await.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{EventEnvelope, GraphEvent, NodeId, RunId, now_ms};

    #[tokio::test]
    async fn tracks_run_lifecycle() {
        let run_id = RunId::new();
        let collector = TraceCollector::new(run_id.clone());

        let start_ts = now_ms();
        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: start_ts }
        )).await;

        let end_ts = start_ts + 500;
        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::RunCompleted { run_id: run_id.clone(), ts: end_ts }
        )).await;

        let trace = collector.snapshot().await;
        assert_eq!(trace.state, RunState::Completed);
        assert_eq!(trace.started_at, Some(start_ts));
        assert_eq!(trace.total_latency_ms, Some(500));
        assert_eq!(trace.event_count, 2);
    }

    #[tokio::test]
    async fn tracks_node_tokens_and_cost() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let collector = TraceCollector::new(run_id.clone());

        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::AgentStarted { node_id: node_id.clone(), model: "claude-sonnet-4-6".to_string(), ts: now_ms() }
        )).await;

        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::AgentCompleted { node_id: node_id.clone(), input_tokens: 1000, output_tokens: 500, ts: now_ms() }
        )).await;

        let trace = collector.snapshot().await;
        let node = trace.nodes.get(&node_id).unwrap();
        assert_eq!(node.input_tokens, 1000);
        assert_eq!(node.model.as_deref(), Some("claude-sonnet-4-6"));
        assert!(node.cost_usd > 0.0);
        assert_eq!(trace.total_input_tokens, 1000);
    }

    #[tokio::test]
    async fn tracks_node_latency() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let collector = TraceCollector::new(run_id.clone());
        let ts = now_ms();

        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::NodeStarted { id: node_id.clone(), ts }
        )).await;

        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts: ts + 300 }
        )).await;

        let trace = collector.snapshot().await;
        let node = trace.nodes.get(&node_id).unwrap();
        assert_eq!(node.latency_ms, Some(300));
        assert_eq!(node.status, NodeStatus::Completed);
    }

    #[tokio::test]
    async fn run_failed_computes_latency() {
        let run_id = RunId::new();
        let collector = TraceCollector::new(run_id.clone());
        let start_ts = now_ms();

        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: start_ts }
        )).await;

        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::RunFailed { run_id: run_id.clone(), error: "boom".to_string(), ts: start_ts + 250 }
        )).await;

        let trace = collector.snapshot().await;
        assert_eq!(trace.state, RunState::Failed);
        assert_eq!(trace.total_latency_ms, Some(250));
    }

    #[tokio::test]
    async fn node_failed_computes_latency() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let collector = TraceCollector::new(run_id.clone());
        let ts = now_ms();

        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::NodeStarted { id: node_id.clone(), ts }
        )).await;

        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::NodeFailed { id: node_id.clone(), error: "oops".to_string(), ts: ts + 400 }
        )).await;

        let trace = collector.snapshot().await;
        let node = trace.nodes.get(&node_id).unwrap();
        assert_eq!(node.latency_ms, Some(400));
        assert_eq!(node.status, NodeStatus::Failed);
    }

    #[tokio::test]
    async fn event_count_increments() {
        let run_id = RunId::new();
        let collector = TraceCollector::new(run_id.clone());
        let ts = now_ms();

        for i in 0..5u64 {
            collector.ingest(&EventEnvelope::new(run_id.clone(), i,
                GraphEvent::RunStarted { run_id: run_id.clone(), ts }
            )).await;
        }

        let trace = collector.snapshot().await;
        assert_eq!(trace.event_count, 5);
    }
}
