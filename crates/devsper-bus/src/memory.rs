use devsper_core::{Bus, BusMessage};
use anyhow::Result;
use async_trait::async_trait;
use std::collections::HashMap;
use std::pin::Pin;
use std::future::Future;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tracing::debug;

/// In-process bus using tokio broadcast channels.
/// Suitable for single-node mode. Not persistent.
pub struct InMemoryBus {
    /// topic → broadcast sender
    channels: Arc<RwLock<HashMap<String, broadcast::Sender<BusMessage>>>>,
}

impl InMemoryBus {
    pub fn new() -> Self {
        Self {
            channels: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    async fn get_or_create_sender(&self, topic: &str) -> broadcast::Sender<BusMessage> {
        {
            let channels = self.channels.read().await;
            if let Some(tx) = channels.get(topic) {
                return tx.clone();
            }
        }
        let mut channels = self.channels.write().await;
        // Double-checked locking
        if let Some(tx) = channels.get(topic) {
            return tx.clone();
        }
        let (tx, _) = broadcast::channel(1024);
        channels.insert(topic.to_string(), tx.clone());
        tx
    }
}

impl Default for InMemoryBus {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Bus for InMemoryBus {
    async fn publish(&self, msg: BusMessage) -> Result<()> {
        let tx = self.get_or_create_sender(&msg.topic).await;
        debug!(topic = %msg.topic, "Bus publish");
        // Ignore send errors (no active receivers)
        let _ = tx.send(msg);
        Ok(())
    }

    async fn subscribe(
        &self,
        topic: &str,
        handler: Box<
            dyn Fn(BusMessage) -> Pin<Box<dyn Future<Output = ()> + Send>>
            + Send + Sync,
        >,
    ) -> Result<()> {
        let tx = self.get_or_create_sender(topic).await;
        let mut rx = tx.subscribe();
        let handler = Arc::new(handler);

        tokio::spawn(async move {
            while let Ok(msg) = rx.recv().await {
                handler(msg).await;
            }
        });

        Ok(())
    }

    async fn start(&self) -> Result<()> {
        Ok(()) // no-op for in-memory bus
    }

    async fn stop(&self) -> Result<()> {
        Ok(()) // no-op for in-memory bus
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::RunId;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[tokio::test]
    async fn publish_subscribe_roundtrip() {
        let bus = InMemoryBus::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let c2 = counter.clone();

        bus.subscribe(
            "test.topic",
            Box::new(move |_msg: BusMessage| {
                let c = c2.clone();
                Box::pin(async move {
                    c.fetch_add(1, Ordering::SeqCst);
                })
            }),
        )
        .await
        .unwrap();

        let msg = BusMessage::new(RunId::new(), "test.topic", serde_json::json!({"x": 1}));
        bus.publish(msg).await.unwrap();

        // Give tokio a moment to deliver
        tokio::time::sleep(tokio::time::Duration::from_millis(20)).await;
        assert_eq!(counter.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn multiple_subscribers_all_receive() {
        let bus = Arc::new(InMemoryBus::new());
        let c1 = Arc::new(AtomicUsize::new(0));
        let c2 = Arc::new(AtomicUsize::new(0));

        let c1c = c1.clone();
        bus.subscribe(
            "shared",
            Box::new(move |_| {
                let c = c1c.clone();
                Box::pin(async move {
                    c.fetch_add(1, Ordering::SeqCst);
                })
            }),
        )
        .await
        .unwrap();

        let c2c = c2.clone();
        bus.subscribe(
            "shared",
            Box::new(move |_| {
                let c = c2c.clone();
                Box::pin(async move {
                    c.fetch_add(1, Ordering::SeqCst);
                })
            }),
        )
        .await
        .unwrap();

        bus.publish(BusMessage::new(RunId::new(), "shared", serde_json::json!(null)))
            .await
            .unwrap();

        tokio::time::sleep(tokio::time::Duration::from_millis(20)).await;
        assert_eq!(c1.load(Ordering::SeqCst), 1);
        assert_eq!(c2.load(Ordering::SeqCst), 1);
    }
}
