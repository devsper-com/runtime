//! Leader election — Redis SET NX + TTL, Lua refresh, watch loop.

use redis::AsyncCommands;

use crate::error::{DevsperError, Result};

const LEADER_KEY_PREFIX: &str = "devsper:leader:";
const LEADER_TTL: u64 = 15;
const REFRESH_INTERVAL_SECS: u64 = 5;

pub struct LeaderElector {
    redis: redis::aio::ConnectionManager,
    key: String,
}

impl LeaderElector {
    pub fn new(redis: redis::aio::ConnectionManager, run_id: &str) -> Self {
        let key = format!("{}{}", LEADER_KEY_PREFIX, run_id);
        Self { redis, key }
    }

    /// SET key node_id NX EX 15. Returns true if this node won.
    pub async fn campaign(&mut self, node_id: &str) -> Result<bool> {
        let result: bool = redis::cmd("SET")
            .arg(&self.key)
            .arg(node_id)
            .arg("NX")
            .arg("EX")
            .arg(LEADER_TTL)
            .query_async(&mut self.redis)
            .await
            .map_err(DevsperError::Redis)?;
        Ok(result)
    }

    /// If current value == node_id, EXPIRE 15 and return true.
    pub async fn refresh(&mut self, node_id: &str) -> Result<bool> {
        let script = r#"
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        "#;
        let result: i32 = redis::Script::new(script)
            .key(&self.key)
            .arg(node_id)
            .arg(LEADER_TTL as i32)
            .invoke_async(&mut self.redis)
            .await
            .map_err(DevsperError::Redis)?;
        Ok(result != 0)
    }

    pub async fn get_leader(&mut self) -> Result<Option<String>> {
        let raw: Option<String> = self.redis.get(&self.key).await?;
        Ok(raw)
    }

    pub async fn abdicate(&mut self, node_id: &str) -> Result<()> {
        let script = r#"
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('DEL', KEYS[1])
        end
        "#;
        let _: () = redis::Script::new(script)
            .key(&self.key)
            .arg(node_id)
            .invoke_async::<_, ()>(&mut self.redis)
            .await
            .map_err(DevsperError::Redis)?;
        Ok(())
    }

    /// Loop: every REFRESH_INTERVAL_SECS, refresh if leader else campaign; call on_elected/on_lost on transition.
    pub async fn watch(
        &mut self,
        node_id: &str,
        mut on_elected: impl FnMut() -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>>,
        mut on_lost: impl FnMut() -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>>,
    ) -> Result<()> {
        let mut currently_leader = false;
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(REFRESH_INTERVAL_SECS)).await;
            if currently_leader {
                if self.refresh(node_id).await? {
                    continue;
                }
                currently_leader = false;
                on_lost().await;
            } else if self.campaign(node_id).await? {
                currently_leader = true;
                on_elected().await;
            }
        }
    }
}
