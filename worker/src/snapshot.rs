//! Scheduler snapshot store — Redis SET/GET.

use redis::AsyncCommands;

use crate::error::Result;

const SNAPSHOT_KEY_PREFIX: &str = "hivemind:snapshot:";
const SNAPSHOT_INDEX_KEY: &str = "hivemind:snapshots";

pub struct SnapshotStore {
    redis: redis::aio::ConnectionManager,
}

impl SnapshotStore {
    pub fn new(redis: redis::aio::ConnectionManager) -> Self {
        Self { redis }
    }

    pub async fn save(&mut self, run_id: &str, snapshot: &serde_json::Value) -> Result<()> {
        let key = format!("{}{}", SNAPSHOT_KEY_PREFIX, run_id);
        let json = serde_json::to_string(snapshot)?;
        self.redis.set::<_, _, ()>(&key, &json).await?;
        self.redis
            .sadd::<_, _, ()>(SNAPSHOT_INDEX_KEY, run_id)
            .await?;
        Ok(())
    }

    pub async fn load(&mut self, run_id: &str) -> Result<Option<serde_json::Value>> {
        let key = format!("{}{}", SNAPSHOT_KEY_PREFIX, run_id);
        let raw: Option<String> = self.redis.get(&key).await?;
        Ok(raw.and_then(|s| serde_json::from_str(&s).ok()))
    }

    pub async fn delete(&mut self, run_id: &str) -> Result<()> {
        let key = format!("{}{}", SNAPSHOT_KEY_PREFIX, run_id);
        self.redis.del::<_, ()>(&key).await?;
        self.redis
            .srem::<_, _, ()>(SNAPSHOT_INDEX_KEY, run_id)
            .await?;
        Ok(())
    }
}
