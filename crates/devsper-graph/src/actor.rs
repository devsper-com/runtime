use crate::{
    event_log::EventLog,
    mutation::{MutationRequest, MutationResult},
    snapshot::build_snapshot,
    validator::MutationValidator,
};
use devsper_core::{
    now_ms, GraphEvent, GraphMutation, GraphSnapshot, Node, NodeId, NodeSpec, NodeStatus, RunId,
};
use petgraph::graph::{DiGraph, NodeIndex};
use std::collections::{HashMap, HashSet};
use tokio::sync::{mpsc, oneshot};
use tracing::{debug, info, warn};

/// Configuration for the graph actor
#[derive(Debug, Clone)]
pub struct GraphConfig {
    pub run_id: RunId,
    pub snapshot_interval: u64,
    pub max_depth: u32,
}

impl Default for GraphConfig {
    fn default() -> Self {
        Self {
            run_id: RunId::new(),
            snapshot_interval: 1000,
            max_depth: 10,
        }
    }
}

/// Messages the GraphActor processes
enum ActorMessage {
    Mutate(MutationRequest),
    GetReady(oneshot::Sender<Vec<NodeId>>),
    ClaimNode(NodeId, oneshot::Sender<bool>),
    CompleteNode(NodeId, serde_json::Value),
    FailNode(NodeId, String),
    GetSnapshot(oneshot::Sender<GraphSnapshot>),
    Shutdown,
}

/// Handle for interacting with a running GraphActor from other tasks
#[derive(Clone)]
pub struct GraphHandle {
    sender: mpsc::Sender<ActorMessage>,
}

impl GraphHandle {
    /// Apply a mutation to the graph. Returns Err if rejected or actor is gone.
    pub async fn mutate(&self, mutation: GraphMutation) -> Result<(), String> {
        let (req, rx) = MutationRequest::new(mutation);
        self.sender
            .send(ActorMessage::Mutate(req))
            .await
            .map_err(|_| "GraphActor has shut down".to_string())?;
        match rx.await.map_err(|_| "GraphActor dropped response".to_string())? {
            MutationResult::Applied => Ok(()),
            MutationResult::Rejected { reason } => Err(reason),
        }
    }

    /// Get all currently ready (runnable) node IDs.
    pub async fn get_ready(&self) -> Vec<NodeId> {
        let (tx, rx) = oneshot::channel();
        let _ = self.sender.send(ActorMessage::GetReady(tx)).await;
        rx.await.unwrap_or_default()
    }

    /// Claim a node for execution (Pending/Ready → Running).
    /// Returns true if this caller won the claim race.
    pub async fn claim(&self, id: NodeId) -> bool {
        let (tx, rx) = oneshot::channel();
        let _ = self.sender.send(ActorMessage::ClaimNode(id, tx)).await;
        rx.await.unwrap_or(false)
    }

    /// Mark a node as completed with its result value.
    pub async fn complete(&self, id: NodeId, result: serde_json::Value) {
        let _ = self.sender.send(ActorMessage::CompleteNode(id, result)).await;
    }

    /// Mark a node as failed with an error message.
    pub async fn fail(&self, id: NodeId, error: String) {
        let _ = self.sender.send(ActorMessage::FailNode(id, error)).await;
    }

    /// Get a point-in-time snapshot of the graph state.
    pub async fn snapshot(&self) -> Option<GraphSnapshot> {
        let (tx, rx) = oneshot::channel();
        let _ = self.sender.send(ActorMessage::GetSnapshot(tx)).await;
        rx.await.ok()
    }

    /// Gracefully shut down the graph actor.
    pub async fn shutdown(&self) {
        let _ = self.sender.send(ActorMessage::Shutdown).await;
    }
}

/// The graph actor — single writer, owns all graph state.
/// Run in a dedicated tokio task via `tokio::spawn(actor.run())`.
pub struct GraphActor {
    config: GraphConfig,
    nodes: HashMap<NodeId, Node>,
    graph: DiGraph<NodeId, ()>,
    index_map: HashMap<NodeId, NodeIndex>,
    ready_set: HashSet<NodeId>,
    event_log: EventLog,
    validator: MutationValidator,
    receiver: mpsc::Receiver<ActorMessage>,
    event_tx: mpsc::Sender<GraphEvent>,
}

impl GraphActor {
    /// Create a new GraphActor.
    /// Returns (actor, handle, event_receiver).
    pub fn new(config: GraphConfig) -> (Self, GraphHandle, mpsc::Receiver<GraphEvent>) {
        let (msg_tx, msg_rx) = mpsc::channel(1024);
        let (event_tx, event_rx) = mpsc::channel(4096);

        let actor = Self {
            event_log: EventLog::new(config.snapshot_interval),
            config,
            nodes: HashMap::new(),
            graph: DiGraph::new(),
            index_map: HashMap::new(),
            ready_set: HashSet::new(),
            validator: MutationValidator::new(),
            receiver: msg_rx,
            event_tx,
        };

        let handle = GraphHandle { sender: msg_tx };
        (actor, handle, event_rx)
    }

    /// Seed the graph with initial nodes before starting the run loop.
    pub fn add_initial_nodes(&mut self, specs: Vec<NodeSpec>) {
        for spec in specs {
            self.add_node_internal(spec);
        }
        // Wire up declared edges
        let pairs: Vec<(NodeId, NodeId)> = self
            .nodes
            .values()
            .flat_map(|n| {
                n.spec
                    .depends_on
                    .iter()
                    .map(|dep| (dep.clone(), n.spec.id.clone()))
                    .collect::<Vec<_>>()
            })
            .collect();
        for (from, to) in pairs {
            if let (Some(&fi), Some(&ti)) =
                (self.index_map.get(&from), self.index_map.get(&to))
            {
                self.graph.add_edge(fi, ti, ());
            }
        }
        self.recompute_ready_set();
    }

    /// Drive the actor message loop. Call via `tokio::spawn(actor.run())`.
    pub async fn run(mut self) {
        info!(run_id = %self.config.run_id, "GraphActor started");

        while let Some(msg) = self.receiver.recv().await {
            match msg {
                ActorMessage::Mutate(req) => self.handle_mutate(req).await,

                ActorMessage::GetReady(tx) => {
                    let ready: Vec<NodeId> = self.ready_set.iter().cloned().collect();
                    debug!(count = ready.len(), "GetReady");
                    let _ = tx.send(ready);
                }

                ActorMessage::ClaimNode(id, tx) => {
                    let ok = self.handle_claim(&id);
                    let _ = tx.send(ok);
                }

                ActorMessage::CompleteNode(id, result) => {
                    self.handle_complete(id, result).await;
                }

                ActorMessage::FailNode(id, error) => {
                    self.handle_fail(id, error).await;
                }

                ActorMessage::GetSnapshot(tx) => {
                    let snap = self.build_current_snapshot();
                    let _ = tx.send(snap);
                }

                ActorMessage::Shutdown => {
                    info!(run_id = %self.config.run_id, "GraphActor shutting down");
                    break;
                }
            }

            // Auto-snapshot when interval is reached
            if self.event_log.should_snapshot() {
                let snap = self.build_current_snapshot();
                self.event_log.record_snapshot(snap.clone());
                self.emit(GraphEvent::SnapshotTaken {
                    snapshot: snap,
                    ts: now_ms(),
                })
                .await;
            }
        }
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    fn add_node_internal(&mut self, spec: NodeSpec) -> NodeIndex {
        let id = spec.id.clone();
        let idx = self.graph.add_node(id.clone());
        self.index_map.insert(id.clone(), idx);
        self.nodes.insert(id, Node::new(spec));
        idx
    }

    fn recompute_ready_set(&mut self) {
        self.ready_set.clear();
        let ids: Vec<NodeId> = self.nodes.keys().cloned().collect();
        for id in ids {
            let node = &self.nodes[&id];
            if node.status != NodeStatus::Pending {
                continue;
            }
            let all_deps_done = node.spec.depends_on.iter().all(|dep_id| {
                self.nodes
                    .get(dep_id)
                    .map(|d| d.status == NodeStatus::Completed)
                    .unwrap_or(false)
            });
            if all_deps_done {
                self.ready_set.insert(id);
            }
        }
    }

    fn handle_claim(&mut self, id: &NodeId) -> bool {
        if !self.ready_set.contains(id) {
            return false;
        }
        if let Some(node) = self.nodes.get_mut(id) {
            if matches!(node.status, NodeStatus::Pending | NodeStatus::Ready) {
                node.status = NodeStatus::Running;
                node.started_at = Some(now_ms());
                self.ready_set.remove(id);
                return true;
            }
        }
        false
    }

    async fn handle_complete(&mut self, id: NodeId, result: serde_json::Value) {
        if let Some(node) = self.nodes.get_mut(&id) {
            node.status = NodeStatus::Completed;
            node.result = Some(result.clone());
            node.completed_at = Some(now_ms());
            self.emit(GraphEvent::NodeCompleted {
                id: id.clone(),
                result,
                ts: now_ms(),
            })
            .await;
        }
        self.recompute_ready_set();
        if self.is_run_complete() {
            self.emit(GraphEvent::RunCompleted {
                run_id: self.config.run_id.clone(),
                ts: now_ms(),
            })
            .await;
        }
    }

    async fn handle_fail(&mut self, id: NodeId, error: String) {
        if let Some(node) = self.nodes.get_mut(&id) {
            node.status = NodeStatus::Failed;
            node.error = Some(error.clone());
            node.completed_at = Some(now_ms());
        }
        self.emit(GraphEvent::NodeFailed {
            id,
            error,
            ts: now_ms(),
        })
        .await;
    }

    async fn handle_mutate(&mut self, req: MutationRequest) {
        match self
            .validator
            .validate(&self.graph, &self.index_map, &req.mutation)
        {
            Err(reason) => {
                warn!("Mutation rejected: {reason}");
                self.emit(GraphEvent::MutationRejected {
                    reason: reason.clone(),
                    ts: now_ms(),
                })
                .await;
                let _ = req.response.send(MutationResult::Rejected { reason });
            }
            Ok(()) => {
                self.apply_mutation(req.mutation.clone()).await;
                self.emit(GraphEvent::MutationApplied {
                    mutation: req.mutation,
                    ts: now_ms(),
                })
                .await;
                let _ = req.response.send(MutationResult::Applied);
                self.recompute_ready_set();
            }
        }
    }

    async fn apply_mutation(&mut self, mutation: GraphMutation) {
        match mutation {
            GraphMutation::AddNode { spec } => {
                let id = spec.id.clone();
                let deps = spec.depends_on.clone();
                self.add_node_internal(spec.clone());
                // Wire declared dependencies
                for dep_id in &deps {
                    if let (Some(&di), Some(&ni)) =
                        (self.index_map.get(dep_id), self.index_map.get(&id))
                    {
                        self.graph.add_edge(di, ni, ());
                        self.emit(GraphEvent::EdgeAdded {
                            from: dep_id.clone(),
                            to: id.clone(),
                            ts: now_ms(),
                        })
                        .await;
                    }
                }
                self.emit(GraphEvent::NodeAdded {
                    id,
                    spec,
                    ts: now_ms(),
                })
                .await;
            }

            GraphMutation::AddEdge { from, to } => {
                if let (Some(&fi), Some(&ti)) =
                    (self.index_map.get(&from), self.index_map.get(&to))
                {
                    self.graph.add_edge(fi, ti, ());
                    self.emit(GraphEvent::EdgeAdded {
                        from,
                        to,
                        ts: now_ms(),
                    })
                    .await;
                }
            }

            GraphMutation::RemoveEdge { from, to } => {
                if let (Some(&fi), Some(&ti)) =
                    (self.index_map.get(&from), self.index_map.get(&to))
                {
                    if let Some(edge) = self.graph.find_edge(fi, ti) {
                        self.graph.remove_edge(edge);
                        self.emit(GraphEvent::EdgeRemoved {
                            from,
                            to,
                            ts: now_ms(),
                        })
                        .await;
                    }
                }
            }

            GraphMutation::InjectBefore { before, insert } => {
                let new_id = insert.id.clone();
                self.add_node_internal(insert.clone());
                self.emit(GraphEvent::NodeAdded {
                    id: new_id.clone(),
                    spec: insert,
                    ts: now_ms(),
                })
                .await;
                // new_node → before
                if let (Some(&ni), Some(&bi)) =
                    (self.index_map.get(&new_id), self.index_map.get(&before))
                {
                    self.graph.add_edge(ni, bi, ());
                    self.emit(GraphEvent::EdgeAdded {
                        from: new_id,
                        to: before,
                        ts: now_ms(),
                    })
                    .await;
                }
            }

            GraphMutation::PruneSubgraph { root } => {
                let to_abandon = self.collect_subgraph(&root);
                for id in to_abandon {
                    if let Some(node) = self.nodes.get_mut(&id) {
                        if !node.is_terminal() {
                            node.status = NodeStatus::Abandoned;
                            self.ready_set.remove(&id);
                            self.emit(GraphEvent::NodeAbandoned {
                                id,
                                ts: now_ms(),
                            })
                            .await;
                        }
                    }
                }
            }

            GraphMutation::SplitNode { node, into } => {
                if let Some(n) = self.nodes.get_mut(&node) {
                    if !n.is_terminal() {
                        n.status = NodeStatus::Abandoned;
                        self.ready_set.remove(&node);
                        self.emit(GraphEvent::NodeAbandoned {
                            id: node,
                            ts: now_ms(),
                        })
                        .await;
                    }
                }
                for spec in into {
                    let id = spec.id.clone();
                    self.add_node_internal(spec.clone());
                    self.emit(GraphEvent::NodeAdded {
                        id,
                        spec,
                        ts: now_ms(),
                    })
                    .await;
                }
            }

            GraphMutation::MarkSpeculative { nodes } => {
                for id in nodes {
                    if let Some(node) = self.nodes.get_mut(&id) {
                        if node.status == NodeStatus::Pending {
                            node.status = NodeStatus::Speculative;
                            self.ready_set.remove(&id);
                        }
                    }
                }
            }

            GraphMutation::ConfirmSpeculative { nodes } => {
                for id in nodes {
                    if let Some(node) = self.nodes.get_mut(&id) {
                        if node.status == NodeStatus::Speculative {
                            node.status = NodeStatus::Pending;
                        }
                    }
                }
                self.recompute_ready_set();
            }

            GraphMutation::DiscardSpeculative { nodes } => {
                for id in nodes {
                    if let Some(node) = self.nodes.get_mut(&id) {
                        if node.status == NodeStatus::Speculative {
                            node.status = NodeStatus::Abandoned;
                            self.ready_set.remove(&id);
                            self.emit(GraphEvent::NodeAbandoned {
                                id,
                                ts: now_ms(),
                            })
                            .await;
                        }
                    }
                }
            }

            GraphMutation::RemoveNode { id } => {
                if let Some(&idx) = self.index_map.get(&id) {
                    self.graph.remove_node(idx);
                    self.nodes.remove(&id);
                    self.ready_set.remove(&id);
                    // petgraph swap-removes; rebuild map so stale indices don't leak
                    self.rebuild_index_map();
                    self.emit(GraphEvent::NodeAbandoned { id, ts: now_ms() }).await;
                }
            }

            GraphMutation::ModifyNode { id, prompt, model } => {
                if let Some(node) = self.nodes.get_mut(&id) {
                    node.spec.prompt = prompt;
                    node.spec.model = model;
                }
            }
        }
    }

    fn rebuild_index_map(&mut self) {
        self.index_map.clear();
        for idx in self.graph.node_indices() {
            if let Some(id) = self.graph.node_weight(idx) {
                self.index_map.insert(id.clone(), idx);
            }
        }
    }

    /// Collect a node and all its descendants (BFS over outgoing edges).
    fn collect_subgraph(&self, root: &NodeId) -> Vec<NodeId> {
        let mut result = Vec::new();
        let Some(&root_idx) = self.index_map.get(root) else {
            return result;
        };
        let mut stack = vec![root_idx];
        let mut visited = HashSet::new();
        while let Some(idx) = stack.pop() {
            if !visited.insert(idx) {
                continue;
            }
            if let Some(id) = self.graph.node_weight(idx) {
                result.push(id.clone());
            }
            for neighbor in self.graph.neighbors(idx) {
                stack.push(neighbor);
            }
        }
        result
    }

    fn build_current_snapshot(&self) -> GraphSnapshot {
        let edges: Vec<(NodeId, NodeId)> = self
            .graph
            .edge_indices()
            .filter_map(|e| {
                self.graph.edge_endpoints(e).and_then(|(fi, ti)| {
                    let from = self.graph.node_weight(fi)?.clone();
                    let to = self.graph.node_weight(ti)?.clone();
                    Some((from, to))
                })
            })
            .collect();

        build_snapshot(
            self.config.run_id.clone(),
            &self.nodes,
            edges,
            self.event_log.len() as u64,
        )
    }

    fn is_run_complete(&self) -> bool {
        !self.nodes.is_empty() && self.nodes.values().all(|n| n.is_terminal())
    }

    async fn emit(&mut self, event: GraphEvent) {
        self.event_log.append(event.clone());
        // Non-blocking: drop events if the consumer is slow
        let _ = self.event_tx.try_send(event);
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{GraphMutation, NodeSpec};

    fn make_config() -> GraphConfig {
        GraphConfig {
            run_id: RunId::new(),
            snapshot_interval: 100,
            max_depth: 10,
        }
    }

    #[tokio::test]
    async fn single_task_ready_and_completes() {
        let (mut actor, handle, _rx) = GraphActor::new(make_config());
        let spec = NodeSpec::new("test task");
        let node_id = spec.id.clone();
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let ready = handle.get_ready().await;
        assert!(ready.contains(&node_id));

        assert!(handle.claim(node_id.clone()).await);

        // No longer in ready set after claim
        let ready2 = handle.get_ready().await;
        assert!(!ready2.contains(&node_id));

        handle.complete(node_id, serde_json::json!({"ok": true})).await;
        handle.shutdown().await;
    }

    #[tokio::test]
    async fn dependency_ordering_respected() {
        let (mut actor, handle, _rx) = GraphActor::new(make_config());

        let spec_a = NodeSpec::new("A");
        let id_a = spec_a.id.clone();
        let spec_b = NodeSpec::new("B").depends_on(vec![id_a.clone()]);
        let id_b = spec_b.id.clone();

        actor.add_initial_nodes(vec![spec_a, spec_b]);
        tokio::spawn(actor.run());

        // Only A ready initially
        let ready = handle.get_ready().await;
        assert!(ready.contains(&id_a), "A should be ready");
        assert!(!ready.contains(&id_b), "B should not be ready yet");

        handle.claim(id_a.clone()).await;
        handle.complete(id_a, serde_json::json!(null)).await;

        tokio::time::sleep(tokio::time::Duration::from_millis(20)).await;

        let ready2 = handle.get_ready().await;
        assert!(ready2.contains(&id_b), "B should be ready after A completes");

        handle.shutdown().await;
    }

    #[tokio::test]
    async fn cycle_mutation_rejected() {
        let (mut actor, handle, _rx) = GraphActor::new(make_config());

        let spec_a = NodeSpec::new("A");
        let id_a = spec_a.id.clone();
        let spec_b = NodeSpec::new("B").depends_on(vec![id_a.clone()]);
        let id_b = spec_b.id.clone();

        actor.add_initial_nodes(vec![spec_a, spec_b]);
        tokio::spawn(actor.run());

        // A→B exists; adding B→A creates a cycle
        let result = handle
            .mutate(GraphMutation::AddEdge {
                from: id_b.clone(),
                to: id_a.clone(),
            })
            .await;
        assert!(result.is_err(), "Cycle should be rejected: {result:?}");

        handle.shutdown().await;
    }

    #[tokio::test]
    async fn inject_node_mutation_makes_it_ready() {
        let (actor, handle, _rx) = GraphActor::new(make_config());
        tokio::spawn(actor.run());

        let new_spec = NodeSpec::new("injected");
        let new_id = new_spec.id.clone();

        handle
            .mutate(GraphMutation::AddNode { spec: new_spec })
            .await
            .unwrap();

        tokio::time::sleep(tokio::time::Duration::from_millis(20)).await;

        let ready = handle.get_ready().await;
        assert!(ready.contains(&new_id), "Injected node should be ready");

        handle.shutdown().await;
    }

    #[tokio::test]
    async fn speculative_lifecycle() {
        let (mut actor, handle, _rx) = GraphActor::new(make_config());
        let spec = NodeSpec::new("speculative");
        let id = spec.id.clone();
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        // Mark speculative → not ready
        handle
            .mutate(GraphMutation::MarkSpeculative {
                nodes: vec![id.clone()],
            })
            .await
            .unwrap();
        tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
        assert!(
            !handle.get_ready().await.contains(&id),
            "Speculative should not be ready"
        );

        // Confirm → ready
        handle
            .mutate(GraphMutation::ConfirmSpeculative {
                nodes: vec![id.clone()],
            })
            .await
            .unwrap();
        tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
        assert!(
            handle.get_ready().await.contains(&id),
            "Confirmed speculative should be ready"
        );

        handle.shutdown().await;
    }

    #[tokio::test]
    async fn snapshot_contains_seeded_nodes() {
        let (mut actor, handle, _rx) = GraphActor::new(make_config());
        let spec = NodeSpec::new("seed");
        let id = spec.id.clone();
        actor.add_initial_nodes(vec![spec]);
        tokio::spawn(actor.run());

        let snap = handle.snapshot().await.unwrap();
        assert!(snap.nodes.contains_key(&id));

        handle.shutdown().await;
    }
}
