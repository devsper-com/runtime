use devsper_core::{GraphMutation, NodeSpec};
use devsper_graph::GraphHandle;
use devsper_scheduler::Scheduler;
use anyhow::Result;
use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::time::{sleep, Duration};
use tracing::{debug, error, info, warn};

/// Output from an agent function: result value and optional graph mutations.
pub struct AgentOutput {
    pub result: serde_json::Value,
    pub mutations: Vec<GraphMutation>,
}

/// The agent function signature.
/// Takes the NodeSpec (task description + metadata).
/// Returns AgentOutput or an error string.
pub type AgentFn = Arc<
    dyn Fn(NodeSpec) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<AgentOutput, String>> + Send>>
        + Send
        + Sync,
>;

/// Configuration for the executor.
#[derive(Debug, Clone)]
pub struct ExecutorConfig {
    /// Maximum number of concurrent tasks.
    pub worker_count: usize,
    /// How often to poll for ready tasks (milliseconds).
    pub poll_interval_ms: u64,
}

impl Default for ExecutorConfig {
    fn default() -> Self {
        Self {
            worker_count: 4,
            poll_interval_ms: 50,
        }
    }
}

/// The executor drives the main run loop.
pub struct Executor {
    config: ExecutorConfig,
    scheduler: Arc<Scheduler>,
    handle: GraphHandle,
    agent_fn: AgentFn,
}

impl Executor {
    pub fn new(
        config: ExecutorConfig,
        scheduler: Arc<Scheduler>,
        handle: GraphHandle,
        agent_fn: AgentFn,
    ) -> Self {
        Self {
            config,
            scheduler,
            handle,
            agent_fn,
        }
    }

    /// Run the executor until all tasks are complete or no progress can be made.
    pub async fn run(self) -> Result<()> {
        let semaphore = Arc::new(Semaphore::new(self.config.worker_count));
        let scheduler = self.scheduler.clone();
        let handle = self.handle.clone();
        let agent_fn = self.agent_fn.clone();
        let poll_ms = self.config.poll_interval_ms;

        info!("Executor started (workers={})", self.config.worker_count);

        let mut stall_count = 0u32;
        const MAX_STALL: u32 = 100; // ~5s with 50ms poll

        loop {
            let ready = scheduler.get_ready().await;

            if ready.is_empty() {
                // Check if run is complete (no pending or running tasks)
                let snap = scheduler.snapshot().await;
                if let Some(snap) = snap {
                    let all_terminal = snap.nodes.values().all(|n| n.is_terminal());
                    if all_terminal && !snap.nodes.is_empty() {
                        info!("All tasks complete. Executor done.");
                        break;
                    }
                    // Some tasks are still running (not terminal), wait for them
                    stall_count += 1;
                    if stall_count > MAX_STALL {
                        warn!(
                            "Executor stalled: no ready tasks and not all terminal after {MAX_STALL} polls"
                        );
                        break;
                    }
                }
                sleep(Duration::from_millis(poll_ms)).await;
                continue;
            }

            stall_count = 0;

            for node_id in ready {
                // Try to claim — only one worker wins the race
                if !scheduler.claim(node_id.clone()).await {
                    continue;
                }

                let permit = semaphore.clone().acquire_owned().await?;
                let sched = scheduler.clone();
                let h = handle.clone();
                let agent = agent_fn.clone();

                // Get the node spec for this task
                let spec = {
                    let snap = sched.snapshot().await;
                    snap.and_then(|s| s.nodes.get(&node_id).map(|n| n.spec.clone()))
                };

                let Some(spec) = spec else {
                    warn!("Could not find spec for claimed node {node_id}");
                    sched.fail(node_id, "spec not found".to_string()).await;
                    drop(permit);
                    continue;
                };

                debug!(node = %node_id, prompt = %spec.prompt, "Dispatching task");

                tokio::spawn(async move {
                    let _permit = permit; // released when task completes
                    match agent(spec).await {
                        Ok(output) => {
                            // Apply any mutations the agent requested
                            for mutation in output.mutations {
                                if let Err(e) = h.mutate(mutation).await {
                                    warn!("Mutation rejected: {e}");
                                }
                            }
                            sched.complete(node_id, output.result).await;
                        }
                        Err(e) => {
                            error!(error = %e, "Task failed");
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
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn make_agent(result: serde_json::Value) -> AgentFn {
        Arc::new(move |_spec: NodeSpec| {
            let result = result.clone();
            Box::pin(async move {
                Ok(AgentOutput {
                    result,
                    mutations: vec![],
                })
            })
        })
    }

    fn make_failing_agent() -> AgentFn {
        Arc::new(|_spec: NodeSpec| {
            Box::pin(async move { Err("agent failed intentionally".to_string()) })
        })
    }

    #[tokio::test]
    async fn runs_single_task_to_completion() {
        let config = GraphConfig {
            run_id: RunId::new(),
            snapshot_interval: 100,
            max_depth: 10,
        };
        let (mut actor, handle, _events) = GraphActor::new(config);

        let spec = NodeSpec::new("hello task");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let executor = Executor::new(
            ExecutorConfig {
                worker_count: 2,
                poll_interval_ms: 10,
            },
            scheduler,
            handle,
            make_agent(serde_json::json!({"output": "done"})),
        );

        executor.run().await.unwrap();
    }

    #[tokio::test]
    async fn runs_linear_chain() {
        let config = GraphConfig {
            run_id: RunId::new(),
            snapshot_interval: 100,
            max_depth: 10,
        };
        let (mut actor, handle, _events) = GraphActor::new(config);

        let spec_a = NodeSpec::new("A");
        let id_a = spec_a.id.clone();
        let spec_b = NodeSpec::new("B").depends_on(vec![id_a.clone()]);
        let id_b = spec_b.id.clone();
        let spec_c = NodeSpec::new("C").depends_on(vec![id_b.clone()]);

        actor.add_initial_nodes(vec![spec_a, spec_b, spec_c]);
        tokio::spawn(actor.run());

        let counter = Arc::new(AtomicUsize::new(0));
        let counter2 = counter.clone();

        let agent: AgentFn = Arc::new(move |_spec: NodeSpec| {
            let c = counter2.clone();
            Box::pin(async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(AgentOutput {
                    result: serde_json::json!(null),
                    mutations: vec![],
                })
            })
        });

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let executor = Executor::new(
            ExecutorConfig {
                worker_count: 4,
                poll_interval_ms: 10,
            },
            scheduler,
            handle,
            agent,
        );

        executor.run().await.unwrap();
        assert_eq!(counter.load(Ordering::SeqCst), 3, "All 3 tasks should run");
    }

    #[tokio::test]
    async fn failed_task_marks_node_failed() {
        let config = GraphConfig {
            run_id: RunId::new(),
            snapshot_interval: 100,
            max_depth: 10,
        };
        let (mut actor, handle, _events) = GraphActor::new(config);
        let spec = NodeSpec::new("doomed");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let h2 = handle.clone();
        let executor = Executor::new(
            ExecutorConfig {
                worker_count: 1,
                poll_interval_ms: 10,
            },
            scheduler,
            handle,
            make_failing_agent(),
        );

        executor.run().await.unwrap();

        let snap = h2.snapshot().await.unwrap();
        let all_terminal = snap.nodes.values().all(|n| n.is_terminal());
        assert!(all_terminal, "All nodes should be terminal after failure");
    }

    #[tokio::test]
    async fn mutation_from_agent_is_applied() {
        use devsper_core::GraphMutation;

        let config = GraphConfig {
            run_id: RunId::new(),
            snapshot_interval: 100,
            max_depth: 10,
        };
        let (mut actor, handle, _events) = GraphActor::new(config);
        let spec = NodeSpec::new("planning task");
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        // Agent injects a new node as a mutation
        let injected_spec = NodeSpec::new("injected subtask");
        let injected_id = injected_spec.id.clone();

        let agent: AgentFn = Arc::new(move |_spec: NodeSpec| {
            let inj = injected_spec.clone();
            Box::pin(async move {
                Ok(AgentOutput {
                    result: serde_json::json!({"planned": true}),
                    mutations: vec![GraphMutation::AddNode { spec: inj }],
                })
            })
        });

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let h2 = handle.clone();
        let executor = Executor::new(
            ExecutorConfig {
                worker_count: 2,
                poll_interval_ms: 10,
            },
            scheduler,
            handle,
            agent,
        );

        executor.run().await.unwrap();

        let snap = h2.snapshot().await.unwrap();
        assert!(
            snap.nodes.contains_key(&injected_id),
            "Injected node should be in the graph"
        );
    }
}
