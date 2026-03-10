//! Redis pub/sub bus — connect, publish, subscribe, channel naming.

use tokio::sync::broadcast;

use crate::error::{HivemindError, Result};
use crate::types::BusMessage;
use redis::AsyncCommands;

fn channel(topic: &str, run_id: &str) -> String {
    if run_id.is_empty() {
        topic.to_string()
    } else {
        format!("{}:{}", topic, run_id)
    }
}

/// Redis pub/sub bus backend.
pub struct RedisBus {
    redis_url: String,
    run_id: String,
    pub_client: Option<redis::aio::ConnectionManager>,
    tx: Option<broadcast::Sender<BusMessage>>,
    _sub_handle: Option<tokio::task::JoinHandle<()>>,
}

impl RedisBus {
    pub fn new(redis_url: String, run_id: String) -> Self {
        Self {
            redis_url,
            run_id,
            pub_client: None,
            tx: None,
            _sub_handle: None,
        }
    }

    /// Start the bus and optionally spawn a subscriber loop for the given topics.
    pub async fn start(&mut self, subscribe_topics: &[&str]) -> Result<()> {
        let client = redis::Client::open(self.redis_url.as_str())
            .map_err(|e| HivemindError::BusConnection(e.to_string()))?;
        let mut conn = redis::aio::ConnectionManager::new(client.clone())
            .await
            .map_err(|e| HivemindError::BusConnection(e.to_string()))?;
        let _: String = redis::cmd("PING")
            .query_async(&mut conn)
            .await
            .map_err(|e| HivemindError::BusConnection(e.to_string()))?;
        self.pub_client = Some(conn);
        let (tx, _) = broadcast::channel(256);
        self.tx = Some(tx.clone());

        if !subscribe_topics.is_empty() {
            let redis_url = self.redis_url.clone();
            let run_id = self.run_id.clone();
            let channels: Vec<String> = subscribe_topics
                .iter()
                .map(|t| channel(t, &run_id))
                .collect();
            let handle = tokio::task::spawn_blocking(move || {
                if let Err(e) = run_subscribe_blocking(&redis_url, &channels, tx) {
                    tracing::warn!("subscribe loop exited: {:?}", e);
                }
            });
            self._sub_handle = Some(handle);
        }
        Ok(())
    }

    pub fn redis_client(&self) -> Option<&redis::aio::ConnectionManager> {
        self.pub_client.as_ref()
    }

    pub async fn publish(&mut self, message: &BusMessage) -> Result<()> {
        let conn = self
            .pub_client
            .as_mut()
            .ok_or_else(|| HivemindError::BusConnection("bus not started".to_string()))?;
        let ch = channel(&message.topic, &self.run_id);
        let json = message.to_json()?;
        conn.publish::<_, _, ()>(ch, json)
            .await
            .map_err(HivemindError::Redis)?;
        Ok(())
    }

    pub fn subscribe(&self) -> broadcast::Receiver<BusMessage> {
        self.tx
            .as_ref()
            .map(|tx| tx.subscribe())
            .expect("bus not started")
    }

    pub fn run_id(&self) -> &str {
        &self.run_id
    }

    pub fn channel_for(&self, topic: &str) -> String {
        channel(topic, &self.run_id)
    }
}

/// Blocking subscribe loop; run in spawn_blocking. Sends received messages to tx.
fn run_subscribe_blocking(
    redis_url: &str,
    channels: &[String],
    tx: broadcast::Sender<BusMessage>,
) -> Result<()> {
    let client =
        redis::Client::open(redis_url).map_err(|e| HivemindError::BusConnection(e.to_string()))?;
    let mut conn = client
        .get_connection()
        .map_err(|e| HivemindError::BusConnection(e.to_string()))?;
    let mut pubsub = conn.as_pubsub();
    for ch in channels {
        pubsub.subscribe(ch).map_err(HivemindError::Redis)?;
    }
    loop {
        let msg = pubsub.get_message().map_err(HivemindError::Redis)?;
        let payload: String = msg.get_payload().map_err(HivemindError::Redis)?;
        if let Ok(bus_msg) = BusMessage::from_json(&payload) {
            let _ = tx.send(bus_msg);
        }
    }
}
