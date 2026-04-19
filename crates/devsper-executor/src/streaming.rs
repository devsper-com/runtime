use devsper_core::{EventBus, EventEnvelope, GraphEvent, GraphMutation, NodeSpec, RunId, now_ms};
use devsper_graph::GraphHandle;
use devsper_scheduler::Scheduler;
use anyhow::Result;
use futures::StreamExt;
use std::pin::Pin;
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};
use tokio::time::{sleep, Duration};
use tracing::{debug, info, warn};

use crate::executor::ExecutorConfig;

/// A chunk emitted by a streaming agent.
pub enum StreamChunk {
    Token(String),
    Done {
        result: serde_json::Value,
        mutations: Vec<GraphMutation>,
    },
    Error(String),
}

/// Agent function that returns a stream of chunks instead of a single future.
pub type StreamingAgentFn = Arc<
    dyn Fn(NodeSpec) -> Pin<Box<dyn futures::Stream<Item = StreamChunk> + Send>>
        + Send
        + Sync,
>;

/// Executor variant that publishes NodeOutput events for each streamed token.
pub struct StreamingExecutor {
    config: ExecutorConfig,
    scheduler: Arc<Scheduler>,
    handle: GraphHandle,
    agent_fn: StreamingAgentFn,
    bus: Arc<dyn EventBus>,
    run_id: RunId,
    sequence: Arc<AtomicU64>,
}

impl StreamingExecutor {
    pub fn new(
        config: ExecutorConfig,
        scheduler: Arc<Scheduler>,
        handle: GraphHandle,
        agent_fn: StreamingAgentFn,
        bus: Arc<dyn EventBus>,
        run_id: RunId,
    ) -> Self {
        Self {
            config,
            scheduler,
            handle,
            agent_fn,
            bus,
            run_id,
            sequence: Arc::new(AtomicU64::new(0)),
        }
    }

    pub async fn run(self) -> Result<()> {
        let semaphore = Arc::new(tokio::sync::Semaphore::new(self.config.worker_count));
        let scheduler = self.scheduler.clone();
        let handle = self.handle.clone();
        let agent_fn = self.agent_fn.clone();
        let poll_ms = self.config.poll_interval_ms;
        let bus = self.bus.clone();
        let run_id = self.run_id.clone();
        let sequence = self.sequence.clone();

        info!("StreamingExecutor started (workers={})", self.config.worker_count);

        let mut stall_count = 0u32;
        const MAX_STALL: u32 = 100;

        loop {
            let ready = scheduler.get_ready().await;

            if ready.is_empty() {
                let snap = scheduler.snapshot().await;
                if let Some(snap) = snap {
                    if !snap.nodes.is_empty() && snap.nodes.values().all(|n| n.is_terminal()) {
                        info!("StreamingExecutor: all tasks complete");
                        break;
                    }
                    stall_count += 1;
                    if stall_count > MAX_STALL {
                        warn!("StreamingExecutor stalled after {MAX_STALL} polls");
                        break;
                    }
                }
                sleep(Duration::from_millis(poll_ms)).await;
                continue;
            }

            stall_count = 0;

            for node_id in ready {
                if !scheduler.claim(node_id.clone()).await {
                    continue;
                }

                let permit = semaphore.clone().acquire_owned().await?;
                let sched = scheduler.clone();
                let h = handle.clone();
                let agent = agent_fn.clone();
                let bus2 = bus.clone();
                let run_id2 = run_id.clone();
                let seq2 = sequence.clone();

                let spec = {
                    let snap = sched.snapshot().await;
                    snap.and_then(|s| s.nodes.get(&node_id).map(|n| n.spec.clone()))
                };

                let Some(spec) = spec else {
                    warn!("No spec for node {node_id}");
                    sched.fail(node_id, "spec not found".to_string()).await;
                    drop(permit);
                    continue;
                };

                debug!(node = %node_id, "Streaming node");

                tokio::spawn(async move {
                    let _permit = permit;

                    macro_rules! publish {
                        ($event:expr) => {{
                            let seq = seq2.fetch_add(1, Ordering::Relaxed);
                            let env = EventEnvelope::new(run_id2.clone(), seq, $event);
                            if let Err(e) = bus2.publish(env).await {
                                warn!("EventBus publish error: {e}");
                            }
                        }};
                    }

                    publish!(GraphEvent::NodeStarted { id: node_id.clone(), ts: now_ms() });

                    let mut stream = agent(spec);
                    let mut final_result: Option<serde_json::Value> = None;
                    let mut error: Option<String> = None;
                    let mut mutations: Vec<GraphMutation> = Vec::new();

                    while let Some(chunk) = stream.next().await {
                        match chunk {
                            StreamChunk::Token(text) => {
                                publish!(GraphEvent::NodeOutput {
                                    id: node_id.clone(),
                                    chunk: text,
                                    ts: now_ms(),
                                });
                            }
                            StreamChunk::Done { result, mutations: m } => {
                                final_result = Some(result);
                                mutations = m;
                                break;
                            }
                            StreamChunk::Error(e) => {
                                error = Some(e);
                                break;
                            }
                        }
                    }

                    for mutation in mutations {
                        if let Err(e) = h.mutate(mutation).await {
                            warn!("Mutation rejected: {e}");
                        }
                    }

                    match (final_result, error) {
                        (Some(result), _) => {
                            publish!(GraphEvent::NodeCompleted {
                                id: node_id.clone(),
                                result: result.clone(),
                                ts: now_ms(),
                            });
                            sched.complete(node_id, result).await;
                        }
                        (None, Some(e)) => {
                            publish!(GraphEvent::NodeFailed {
                                id: node_id.clone(),
                                error: e.clone(),
                                ts: now_ms(),
                            });
                            sched.fail(node_id, e).await;
                        }
                        _ => {
                            let e = "stream ended without result".to_string();
                            publish!(GraphEvent::NodeFailed {
                                id: node_id.clone(),
                                error: e.clone(),
                                ts: now_ms(),
                            });
                            sched.fail(node_id, e).await;
                        }
                    }
                });
            }

            sleep(Duration::from_millis(poll_ms)).await;
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{NodeSpec, RunId};
    use devsper_graph::{GraphActor, GraphConfig};
    use futures::stream;

    fn make_streaming_agent(tokens: Vec<&'static str>, result: serde_json::Value) -> StreamingAgentFn {
        Arc::new(move |_spec: NodeSpec| {
            let tokens = tokens.clone();
            let result = result.clone();
            Box::pin(stream::iter(
                tokens
                    .into_iter()
                    .map(|t| StreamChunk::Token(t.to_string()))
                    .chain(std::iter::once(StreamChunk::Done {
                        result,
                        mutations: vec![],
                    })),
            ))
        })
    }

    fn make_config() -> GraphConfig {
        GraphConfig { run_id: RunId::new(), snapshot_interval: 100, max_depth: 10 }
    }

    #[tokio::test]
    async fn streaming_executor_completes_single_task() {
        use devsper_bus::InMemoryEventBus;

        let run_id = RunId::new();
        let config = make_config();
        let (mut actor, handle, _events) = GraphActor::new(config);
        let spec = NodeSpec::new("stream task");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let bus: Arc<dyn EventBus> = Arc::new(InMemoryEventBus::new());
        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let agent = make_streaming_agent(vec!["hello ", "world"], serde_json::json!({"done": true}));

        let executor = StreamingExecutor::new(
            ExecutorConfig { worker_count: 2, poll_interval_ms: 10 },
            scheduler,
            handle.clone(),
            agent,
            bus,
            run_id,
        );

        executor.run().await.unwrap();

        let snap = handle.snapshot().await.unwrap();
        assert!(snap.nodes.values().all(|n| n.is_terminal()));
    }

    #[tokio::test]
    async fn streaming_executor_publishes_node_output_events() {
        use devsper_bus::InMemoryEventBus;
        use devsper_core::GraphEvent;

        let run_id = RunId::new();
        let config = make_config();
        let (mut actor, handle, _events) = GraphActor::new(config);
        let spec = NodeSpec::new("stream task");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let bus = Arc::new(InMemoryEventBus::new());
        let bus_dyn: Arc<dyn EventBus> = bus.clone();

        let mut event_stream = bus.subscribe(&run_id).await.unwrap();

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let agent = make_streaming_agent(vec!["tok1", "tok2", "tok3"], serde_json::json!(null));

        let executor = StreamingExecutor::new(
            ExecutorConfig { worker_count: 1, poll_interval_ms: 10 },
            scheduler,
            handle,
            agent,
            bus_dyn,
            run_id.clone(),
        );

        let executor_task = tokio::spawn(async move { executor.run().await });

        let mut token_count = 0usize;
        let deadline = tokio::time::Instant::now() + Duration::from_secs(3);

        loop {
            let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
            match tokio::time::timeout(remaining, futures::StreamExt::next(&mut event_stream)).await {
                Ok(Some(env)) => {
                    if matches!(env.event, GraphEvent::NodeOutput { .. }) {
                        token_count += 1;
                    }
                    if matches!(env.event, GraphEvent::NodeCompleted { .. }) {
                        break;
                    }
                }
                _ => break,
            }
        }

        executor_task.await.unwrap().unwrap();
        assert_eq!(token_count, 3, "Expected 3 NodeOutput events");
    }

    #[tokio::test]
    async fn streaming_executor_handles_error_stream() {
        use devsper_bus::InMemoryEventBus;

        let run_id = RunId::new();
        let config = make_config();
        let (mut actor, handle, _events) = GraphActor::new(config);
        let spec = NodeSpec::new("failing stream task");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let bus: Arc<dyn EventBus> = Arc::new(InMemoryEventBus::new());
        let scheduler = Arc::new(Scheduler::new(handle.clone()));

        let agent: StreamingAgentFn = Arc::new(|_spec: NodeSpec| {
            Box::pin(stream::iter(vec![StreamChunk::Error("exploded".to_string())]))
        });

        let executor = StreamingExecutor::new(
            ExecutorConfig { worker_count: 1, poll_interval_ms: 10 },
            scheduler,
            handle.clone(),
            agent,
            bus,
            run_id,
        );

        executor.run().await.unwrap();

        let snap = handle.snapshot().await.unwrap();
        assert!(snap.nodes.values().all(|n| n.is_terminal()));
    }
}
