use anyhow::{anyhow, Result};
use async_trait::async_trait;
/// Kafka bus backend using `rdkafka` for distributed event streaming.
///
/// Events are published to a Kafka topic keyed by `run_id` for correct
/// partition routing.  A background consumer task deserialises incoming
/// messages and fans them out to run-scoped **broadcast** channels so that
/// same-process subscribers receive events through the same
/// `Stream<Item = EventEnvelope>` interface used by the in-memory bus.
use devsper_core::{EventBus, EventEnvelope, RunId};
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{Consumer, StreamConsumer};
use rdkafka::message::Message;
use rdkafka::producer::{FutureProducer, FutureRecord};
use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tokio_stream::{Stream, StreamExt};
use tracing::{info, warn};

/// Capacity of each run-scoped broadcast channel.
const CHANNEL_CAPACITY: usize = 4096;

pub struct KafkaBus {
    producer: FutureProducer,
    /// Run-scoped broadcast channels for local subscribers.
    channels: Arc<RwLock<HashMap<String, broadcast::Sender<EventEnvelope>>>>,
    topic_prefix: String,
}

impl KafkaBus {
    /// Create a new `KafkaBus`.
    ///
    /// * `brokers`   – list of broker addresses (e.g. `["localhost:9092"]`).
    /// * `group_id`  – consumer group id shared by all instances that should
    ///                  receive events cooperatively.
    pub fn new(brokers: &[String], group_id: &str) -> Result<Self> {
        let broker_string = brokers.join(",");

        // ── Producer ────────────────────────────────────────────────────
        let producer: FutureProducer = ClientConfig::new()
            .set("bootstrap.servers", &broker_string)
            .set("message.timeout.ms", "5000")
            .set("compression.type", "snappy")
            .create()
            .map_err(|e| anyhow!("Failed to create Kafka producer: {e}"))?;

        // ── Consumer (background task) ──────────────────────────────────
        let channels: Arc<RwLock<HashMap<String, broadcast::Sender<EventEnvelope>>>> =
            Arc::new(RwLock::new(HashMap::new()));

        let consumer: StreamConsumer = ClientConfig::new()
            .set("bootstrap.servers", &broker_string)
            .set("group.id", group_id)
            .set("auto.offset.reset", "latest")
            .set("enable.auto.commit", "true")
            .set("session.timeout.ms", "10000")
            .create()
            .map_err(|e| anyhow!("Failed to create Kafka consumer: {e}"))?;

        let topic_prefix = "devsper.events".to_string();
        let events_topic = format!("{topic_prefix}.graph");

        consumer
            .subscribe(&[&events_topic])
            .map_err(|e| anyhow!("Failed to subscribe to {events_topic}: {e}"))?;

        // Spawn a long-lived task that reads from Kafka and routes envelopes
        // into the appropriate broadcast channel.
        let channels_clone = channels.clone();
        tokio::spawn(async move {
            let mut message_stream = consumer.stream();

            while let Some(message) = message_stream.next().await {
                match message {
                    Ok(msg) => {
                        if let Some(payload) = msg.payload() {
                            match serde_json::from_slice::<EventEnvelope>(payload) {
                                Ok(envelope) => {
                                    let run_id = envelope.run_id.0.clone();
                                    let channels = channels_clone.read().await;
                                    if let Some(tx) = channels.get(&run_id) {
                                        let _ = tx.send(envelope);
                                    }
                                }
                                Err(e) => {
                                    warn!("Failed to deserialize event envelope: {e}");
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!("Kafka consumer error: {e}");
                    }
                }
            }
            info!("Kafka consumer stream ended");
        });

        info!(
            "KafkaBus connected to {} (group: {}, topic: {})",
            broker_string, group_id, events_topic
        );

        Ok(Self {
            producer,
            channels,
            topic_prefix,
        })
    }

    /// Full Kafka topic name for graph events.
    fn events_topic(&self) -> String {
        format!("{}.graph", self.topic_prefix)
    }

    /// Return (or lazily create) the broadcast sender for a given `run_id`.
    async fn sender_for(&self, run_id: &RunId) -> broadcast::Sender<EventEnvelope> {
        let key = run_id.0.clone();
        {
            let r = self.channels.read().await;
            if let Some(tx) = r.get(&key) {
                return tx.clone();
            }
        }
        let mut w = self.channels.write().await;
        w.entry(key)
            .or_insert_with(|| broadcast::channel(CHANNEL_CAPACITY).0)
            .clone()
    }
}

#[async_trait]
impl EventBus for KafkaBus {
    async fn publish(&self, envelope: EventEnvelope) -> Result<()> {
        let topic = self.events_topic();
        let key = envelope.run_id.0.clone();
        let payload =
            serde_json::to_vec(&envelope).map_err(|e| anyhow!("serialize envelope: {e}"))?;

        let record = FutureRecord::to(&topic).payload(&payload).key(&key);

        let delivery_future = self
            .producer
            .send_result(record)
            .map_err(|(e, _)| anyhow!("Kafka produce error: {e}"))?;

        delivery_future
            .await
            .map_err(|_| anyhow!("Kafka delivery future cancelled"))?
            .map_err(|(e, _)| anyhow!("Kafka delivery error: {e:?}"))?;

        // Also fan out to the local broadcast channel so same-process
        // subscribers receive the event immediately without waiting for
        // the round-trip through Kafka.
        let tx = self.sender_for(&envelope.run_id).await;
        let _ = tx.send(envelope);

        Ok(())
    }

    async fn subscribe(
        &self,
        run_id: &RunId,
    ) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>> {
        let tx = self.sender_for(run_id).await;
        let rx = tx.subscribe();
        let stream = tokio_stream::wrappers::BroadcastStream::new(rx).filter_map(|r| r.ok());
        Ok(Box::pin(stream))
    }
}
