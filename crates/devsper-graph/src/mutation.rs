use devsper_core::GraphMutation;
use tokio::sync::oneshot;

/// A request to mutate the graph, with a response channel
pub struct MutationRequest {
    pub mutation: GraphMutation,
    pub response: oneshot::Sender<MutationResult>,
}

/// Result of applying a mutation
#[derive(Debug)]
pub enum MutationResult {
    Applied,
    Rejected { reason: String },
}

impl MutationRequest {
    pub fn new(mutation: GraphMutation) -> (Self, oneshot::Receiver<MutationResult>) {
        let (tx, rx) = oneshot::channel();
        (Self { mutation, response: tx }, rx)
    }
}
