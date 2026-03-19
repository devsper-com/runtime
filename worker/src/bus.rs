//! Redis pub/sub bus — connect, publish, subscribe, channel naming.

use tokio::sync::broadcast;

use crate::error::{DevsperError, Result};
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
            .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
        let mut conn = redis::aio::ConnectionManager::new(client.clone())
            .await
            .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
        let _: String = redis::cmd("PING")
            .query_async(&mut conn)
            .await
            .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
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
        let ch = channel(&message.topic, &self.run_id);
        self.publish_to_channel(&ch, message).await
    }

    /// Publish to an exact channel name (e.g. clarification.request.{run_id} where Python subscribes with run_id=None).
    pub async fn publish_to_channel(&mut self, channel_name: &str, message: &BusMessage) -> Result<()> {
        let conn = self
            .pub_client
            .as_mut()
            .ok_or_else(|| DevsperError::BusConnection("bus not started".to_string()))?;
        let json = message.to_json()?;
        conn.publish::<_, _, ()>(channel_name, json)
            .await
            .map_err(DevsperError::Redis)?;
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

    /// Subscribe to a single channel by full name, wait for one message, then return.
    /// Used for clarification.response (channel = topic:run_id with topic = clarification.response.{run_id}.{request_id}).
    /// Uses a new blocking Redis connection so it does not interfere with the main subscriber.
    pub async fn recv_once_on_channel(
        redis_url: &str,
        channel_name: &str,
        timeout_secs: u64,
    ) -> Result<Option<serde_json::Value>> {
        let url = redis_url.to_string();
        let ch = channel_name.to_string();
        let result = tokio::task::spawn_blocking(move || {
            let client = redis::Client::open(url.as_str())
                .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
            let mut conn = client
                .get_connection()
                .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
            let mut pubsub = conn.as_pubsub();
            pubsub.subscribe(ch.as_str()).map_err(DevsperError::Redis)?;
            let deadline = std::time::Instant::now()
                + std::time::Duration::from_secs(timeout_secs);
            while std::time::Instant::now() < deadline {
                match pubsub.get_message() {
                    Ok(msg) => {
                        let payload: String = msg.get_payload().map_err(DevsperError::Redis)?;
                        let parsed: serde_json::Value =
                            serde_json::from_str(&payload).unwrap_or(serde_json::Value::Null);
                        if let Some(obj) = parsed.get("payload").cloned() {
                            return Ok(Some(obj));
                        }
                        return Ok(Some(parsed));
                    }
                    Err(e) => {
                        tracing::warn!("clarification recv_once error: {:?}", e);
                    }
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Ok(None)
        })
        .await
        .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
        result
    }
}

/// Blocking subscribe loop; run in spawn_blocking. Sends received messages to tx.
fn run_subscribe_blocking(
    redis_url: &str,
    channels: &[String],
    tx: broadcast::Sender<BusMessage>,
) -> Result<()> {
    let client =
        redis::Client::open(redis_url).map_err(|e| DevsperError::BusConnection(e.to_string()))?;
    let mut conn = client
        .get_connection()
        .map_err(|e| DevsperError::BusConnection(e.to_string()))?;
    let mut pubsub = conn.as_pubsub();
    for ch in channels {
        pubsub.subscribe(ch).map_err(DevsperError::Redis)?;
    }
    loop {
        let msg = pubsub.get_message().map_err(DevsperError::Redis)?;
        let payload: String = msg.get_payload().map_err(DevsperError::Redis)?;
        if let Ok(bus_msg) = BusMessage::from_json(&payload) {
            let _ = tx.send(bus_msg);
        }
    }
}
