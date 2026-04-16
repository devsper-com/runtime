use crate::peer::PeerInfo;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;

/// Registry of known cluster workers
pub struct WorkerRegistry {
    peers: Arc<RwLock<HashMap<String, PeerInfo>>>,
    heartbeat_timeout_ms: u64,
}

impl WorkerRegistry {
    pub fn new(heartbeat_timeout_ms: u64) -> Self {
        Self {
            peers: Arc::new(RwLock::new(HashMap::new())),
            heartbeat_timeout_ms,
        }
    }

    pub async fn register(&self, peer: PeerInfo) {
        info!(peer_id = %peer.id, address = %peer.address, "Peer registered");
        self.peers.write().await.insert(peer.id.clone(), peer);
    }

    pub async fn heartbeat(&self, peer_id: &str) {
        let mut peers = self.peers.write().await;
        if let Some(peer) = peers.get_mut(peer_id) {
            peer.last_seen_ms = devsper_core::now_ms();
        }
    }

    pub async fn alive_peers(&self) -> Vec<PeerInfo> {
        let peers = self.peers.read().await;
        peers
            .values()
            .filter(|p| p.is_alive(self.heartbeat_timeout_ms))
            .cloned()
            .collect()
    }

    pub async fn all_peers(&self) -> Vec<PeerInfo> {
        self.peers.read().await.values().cloned().collect()
    }

    pub async fn remove(&self, peer_id: &str) {
        self.peers.write().await.remove(peer_id);
    }
}

impl Default for WorkerRegistry {
    fn default() -> Self {
        Self::new(5000)
    }
}
