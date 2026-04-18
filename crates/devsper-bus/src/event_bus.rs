use devsper_core::{EventBus, EventEnvelope, RunId};
use anyhow::Result;
use async_trait::async_trait;
use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tokio_stream::{wrappers::BroadcastStream, Stream, StreamExt};

const CHANNEL_CAPACITY: usize = 4096;

pub struct InMemoryEventBus {
    channels: Arc<RwLock<HashMap<String, broadcast::Sender<EventEnvelope>>>>,
}

impl InMemoryEventBus {
    pub fn new() -> Self {
        Self { channels: Arc::new(RwLock::new(HashMap::new())) }
    }

    async fn sender_for(&self, run_id: &RunId) -> broadcast::Sender<EventEnvelope> {
        let key = run_id.0.clone();
        {
            let r = self.channels.read().await;
            if let Some(tx) = r.get(&key) { return tx.clone(); }
        }
        let mut w = self.channels.write().await;
        w.entry(key).or_insert_with(|| broadcast::channel(CHANNEL_CAPACITY).0).clone()
    }
}

impl Default for InMemoryEventBus {
    fn default() -> Self { Self::new() }
}

#[async_trait]
impl EventBus for InMemoryEventBus {
    async fn publish(&self, envelope: EventEnvelope) -> Result<()> {
        let tx = self.sender_for(&envelope.run_id).await;
        let _ = tx.send(envelope);
        Ok(())
    }

    async fn subscribe(&self, run_id: &RunId) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>> {
        let tx = self.sender_for(run_id).await;
        let rx = tx.subscribe();
        let stream = BroadcastStream::new(rx).filter_map(|r: Result<EventEnvelope, _>| r.ok());
        Ok(Box::pin(stream))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{GraphEvent, now_ms};
    use tokio_stream::StreamExt;

    #[tokio::test]
    async fn subscribe_receives_published_events() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();
        let mut stream = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let received = tokio::time::timeout(
            std::time::Duration::from_millis(200),
            stream.next(),
        ).await.unwrap().unwrap();
        assert_eq!(received.event_id, env.event_id);
    }

    #[tokio::test]
    async fn events_routed_by_run_id() {
        let bus = InMemoryEventBus::new();
        let run_a = RunId::new();
        let run_b = RunId::new();
        let mut stream_a = bus.subscribe(&run_a).await.unwrap();

        let env_b = EventEnvelope::new(
            run_b.clone(), 1,
            GraphEvent::RunStarted { run_id: run_b.clone(), ts: now_ms() },
        );
        bus.publish(env_b).await.unwrap();

        let result = tokio::time::timeout(
            std::time::Duration::from_millis(50),
            stream_a.next(),
        ).await;
        assert!(result.is_err(), "stream_a must not receive run_b events");
    }

    #[tokio::test]
    async fn multiple_subscribers_same_run() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();
        let mut s1 = bus.subscribe(&run_id).await.unwrap();
        let mut s2 = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunCompleted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let r1 = tokio::time::timeout(std::time::Duration::from_millis(200), s1.next()).await.unwrap().unwrap();
        let r2 = tokio::time::timeout(std::time::Duration::from_millis(200), s2.next()).await.unwrap().unwrap();
        assert_eq!(r1.event_id, env.event_id);
        assert_eq!(r2.event_id, env.event_id);
    }

    #[tokio::test]
    async fn publish_before_subscribe_does_not_panic() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();
        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        // No subscribers — should not panic
        bus.publish(env).await.unwrap();
    }
}
