use devsper_core::{EventBus, EventEnvelope, RunId};
use anyhow::{Context, Result};
use async_trait::async_trait;
use futures::StreamExt;
use std::pin::Pin;
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, Stream};

pub struct RedisBus {
    client: redis::Client,
}

impl RedisBus {
    pub async fn new(url: &str) -> Result<Self> {
        let client = redis::Client::open(url)
            .context("invalid Redis URL")?;
        let mut conn = client.get_multiplexed_async_connection().await
            .context("cannot connect to Redis")?;
        redis::cmd("PING").query_async::<String>(&mut conn).await
            .context("Redis PING failed")?;
        Ok(Self { client })
    }

    fn channel_key(run_id: &RunId) -> String {
        format!("devsper:events:{}", run_id.0)
    }
}

#[async_trait]
impl EventBus for RedisBus {
    async fn publish(&self, envelope: EventEnvelope) -> Result<()> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let payload = serde_json::to_string(&envelope)?;
        let channel = Self::channel_key(&envelope.run_id);
        redis::cmd("PUBLISH")
            .arg(&channel)
            .arg(&payload)
            .query_async::<i64>(&mut conn)
            .await?;
        Ok(())
    }

    async fn subscribe(&self, run_id: &RunId) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>> {
        let mut pubsub = self.client.get_async_pubsub().await?;
        let channel = Self::channel_key(run_id);
        pubsub.subscribe(&channel).await?;

        let (tx, rx) = mpsc::channel::<EventEnvelope>(4096);

        tokio::spawn(async move {
            let mut msg_stream = pubsub.into_on_message();
            while let Some(msg) = msg_stream.next().await {
                if let Ok(payload) = msg.get_payload::<String>() {
                    if let Ok(env) = serde_json::from_str::<EventEnvelope>(&payload) {
                        if tx.send(env).await.is_err() {
                            break;
                        }
                    }
                }
            }
        });

        Ok(Box::pin(ReceiverStream::new(rx)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{GraphEvent, now_ms};

    fn redis_url() -> Option<String> {
        std::env::var("REDIS_URL").ok()
    }

    #[tokio::test]
    async fn redis_pubsub_roundtrip() {
        let url = match redis_url() {
            Some(u) => u,
            None => { eprintln!("REDIS_URL not set, skipping redis test"); return; }
        };
        let bus = RedisBus::new(&url).await.unwrap();
        let run_id = RunId::new();
        let mut stream = bus.subscribe(&run_id).await.unwrap();

        // Give pubsub time to register
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let received = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            tokio_stream::StreamExt::next(&mut stream),
        ).await.unwrap().unwrap();
        assert_eq!(received.event_id, env.event_id);
    }
}
