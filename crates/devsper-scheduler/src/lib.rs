use devsper_core::{GraphSnapshot, NodeId};
use devsper_graph::GraphHandle;

/// Wraps GraphHandle with a scheduler-oriented API.
/// All state lives in the GraphActor; this is a coordination facade.
pub struct Scheduler {
    handle: GraphHandle,
}

impl Scheduler {
    pub fn new(handle: GraphHandle) -> Self {
        Self { handle }
    }

    /// Returns currently runnable node IDs.
    pub async fn get_ready(&self) -> Vec<NodeId> {
        self.handle.get_ready().await
    }

    /// Claim a node for execution. Returns true if this caller won the race.
    pub async fn claim(&self, id: NodeId) -> bool {
        self.handle.claim(id).await
    }

    /// Mark a node completed with its result.
    pub async fn complete(&self, id: NodeId, result: serde_json::Value) {
        self.handle.complete(id, result).await;
    }

    /// Mark a node failed.
    pub async fn fail(&self, id: NodeId, error: String) {
        self.handle.fail(id, error).await;
    }

    /// Get a snapshot of current graph state.
    pub async fn snapshot(&self) -> Option<GraphSnapshot> {
        self.handle.snapshot().await
    }

    /// Access the underlying GraphHandle (for mutations).
    pub fn handle(&self) -> &GraphHandle {
        &self.handle
    }
}
