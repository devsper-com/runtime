use crate::{
    peer::PeerInfo,
    protocol::{ClusterMessage, ClusterMessageKind},
    registry::WorkerRegistry,
};
use devsper_core::now_ms;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use tracing::{info, warn};
use uuid::Uuid;

/// Role of this node in the cluster
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NodeRole {
    Coordinator,
    Worker,
    Candidate,
}

/// Configuration for a cluster node
#[derive(Debug, Clone)]
pub struct ClusterConfig {
    /// This node's ID
    pub node_id: String,
    /// Address to listen on (e.g. "0.0.0.0:7000")
    pub listen_address: String,
    /// Addresses of known peer nodes
    pub known_peers: Vec<String>,
    /// Heartbeat interval in milliseconds
    pub heartbeat_interval_ms: u64,
    /// Heartbeat timeout before considering peer dead
    pub heartbeat_timeout_ms: u64,
}

impl Default for ClusterConfig {
    fn default() -> Self {
        Self {
            node_id: Uuid::new_v4().to_string(),
            listen_address: "0.0.0.0:7000".to_string(),
            known_peers: vec![],
            heartbeat_interval_ms: 1000,
            heartbeat_timeout_ms: 5000,
        }
    }
}

/// A cluster node — can be coordinator or worker
pub struct ClusterNode {
    pub config: ClusterConfig,
    pub role: Arc<RwLock<NodeRole>>,
    pub registry: Arc<WorkerRegistry>,
    pub term: Arc<RwLock<u64>>,
    /// Channel for outgoing messages to send to peers
    pub outbox: mpsc::Sender<ClusterMessage>,
    outbox_rx: Option<mpsc::Receiver<ClusterMessage>>,
}

impl ClusterNode {
    pub fn new(config: ClusterConfig) -> Self {
        let (tx, rx) = mpsc::channel(1024);
        Self {
            registry: Arc::new(WorkerRegistry::new(config.heartbeat_timeout_ms)),
            config,
            role: Arc::new(RwLock::new(NodeRole::Worker)),
            term: Arc::new(RwLock::new(0)),
            outbox: tx,
            outbox_rx: Some(rx),
        }
    }

    /// Take the outbox receiver (call once to wire up transport)
    pub fn take_outbox_rx(&mut self) -> Option<mpsc::Receiver<ClusterMessage>> {
        self.outbox_rx.take()
    }

    pub async fn role(&self) -> NodeRole {
        self.role.read().await.clone()
    }

    pub async fn become_coordinator(&self) {
        let mut role = self.role.write().await;
        *role = NodeRole::Coordinator;
        let term = *self.term.read().await;
        info!(node_id = %self.config.node_id, "Became coordinator");

        let _ = self
            .outbox
            .send(ClusterMessage::new(
                &self.config.node_id,
                ClusterMessageKind::LeaderElected {
                    leader_id: self.config.node_id.clone(),
                    term,
                },
            ))
            .await;
    }

    /// Process an incoming message from another peer
    pub async fn handle_message(&self, msg: ClusterMessage) {
        match &msg.kind {
            ClusterMessageKind::Hello {
                address,
                capabilities,
            } => {
                let peer = PeerInfo {
                    id: msg.from.clone(),
                    address: address.clone(),
                    role: "worker".to_string(),
                    last_seen_ms: now_ms(),
                    capabilities: capabilities.clone(),
                };
                self.registry.register(peer).await;
            }

            ClusterMessageKind::Heartbeat { .. } => {
                self.registry.heartbeat(&msg.from).await;
            }

            ClusterMessageKind::VoteRequest { term, candidate_id } => {
                let current_term = *self.term.read().await;
                let granted = *term > current_term;
                if granted {
                    *self.term.write().await = *term;
                }
                let response = ClusterMessage::new(
                    &self.config.node_id,
                    ClusterMessageKind::VoteResponse {
                        term: *term,
                        granted,
                    },
                )
                .to_peer(candidate_id.clone());
                let _ = self.outbox.send(response).await;
            }

            ClusterMessageKind::LeaderElected { leader_id, term } => {
                info!(leader = %leader_id, term = %term, "Leader elected");
                *self.term.write().await = *term;
                if leader_id == &self.config.node_id {
                    *self.role.write().await = NodeRole::Coordinator;
                } else {
                    *self.role.write().await = NodeRole::Worker;
                }
            }

            _ => {
                warn!(kind = ?msg.kind, "Unhandled cluster message kind (stub)");
            }
        }
    }

    /// Start a leader election (when no heartbeat from coordinator)
    pub async fn start_election(&self) {
        let new_term = {
            let mut term = self.term.write().await;
            *term += 1;
            *term
        };
        *self.role.write().await = NodeRole::Candidate;
        info!(node_id = %self.config.node_id, term = new_term, "Starting election");

        let vote_req = ClusterMessage::new(
            &self.config.node_id,
            ClusterMessageKind::VoteRequest {
                term: new_term,
                candidate_id: self.config.node_id.clone(),
            },
        );
        let _ = self.outbox.send(vote_req).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::ClusterMessageKind;

    #[tokio::test]
    async fn new_node_starts_as_worker() {
        let node = ClusterNode::new(ClusterConfig::default());
        assert_eq!(node.role().await, NodeRole::Worker);
    }

    #[tokio::test]
    async fn become_coordinator_changes_role() {
        let node = ClusterNode::new(ClusterConfig::default());
        node.become_coordinator().await;
        assert_eq!(node.role().await, NodeRole::Coordinator);
    }

    #[tokio::test]
    async fn hello_message_registers_peer() {
        let node = ClusterNode::new(ClusterConfig::default());
        let msg = ClusterMessage::new(
            "peer-1",
            ClusterMessageKind::Hello {
                address: "10.0.0.1:7000".to_string(),
                capabilities: vec!["executor".to_string()],
            },
        );
        node.handle_message(msg).await;
        let peers = node.registry.all_peers().await;
        assert_eq!(peers.len(), 1);
        assert_eq!(peers[0].id, "peer-1");
    }

    #[tokio::test]
    async fn vote_request_grants_for_higher_term() {
        let mut node = ClusterNode::new(ClusterConfig::default());
        let mut rx = node.take_outbox_rx().unwrap();

        let msg = ClusterMessage::new(
            "candidate-1",
            ClusterMessageKind::VoteRequest {
                term: 5,
                candidate_id: "candidate-1".to_string(),
            },
        );
        node.handle_message(msg).await;

        let response = rx.recv().await.unwrap();
        match response.kind {
            ClusterMessageKind::VoteResponse { granted, term } => {
                assert!(granted);
                assert_eq!(term, 5);
            }
            other => panic!("expected VoteResponse, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn election_increments_term() {
        let mut node = ClusterNode::new(ClusterConfig::default());
        let mut rx = node.take_outbox_rx().unwrap();

        node.start_election().await;

        let msg = rx.recv().await.unwrap();
        match msg.kind {
            ClusterMessageKind::VoteRequest { term, .. } => {
                assert_eq!(term, 1);
            }
            other => panic!("expected VoteRequest, got {other:?}"),
        }
    }
}
