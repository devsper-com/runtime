//! Cluster registry — Redis hash HSET/HGETALL/HDEL.

use redis::AsyncCommands;

use crate::error::Result;
use crate::types::NodeInfo;

const REGISTRY_KEY_PREFIX: &str = "hivemind:cluster:";
const REGISTRY_NODES_SUFFIX: &str = ":nodes";
const REGISTRY_TTL: u64 = 60;

pub struct ClusterRegistry {
    redis: redis::aio::ConnectionManager,
    key: String,
}

impl ClusterRegistry {
    pub fn new(redis: redis::aio::ConnectionManager, run_id: &str) -> Self {
        let key = format!("{}{}{}", REGISTRY_KEY_PREFIX, run_id, REGISTRY_NODES_SUFFIX);
        Self { redis, key }
    }

    pub async fn register(&mut self, node: &NodeInfo) -> Result<()> {
        let json = node.to_json()?;
        self.redis
            .hset::<_, _, _, ()>(&self.key, &node.node_id, json)
            .await?;
        self.redis
            .expire::<_, ()>(&self.key, REGISTRY_TTL as i64)
            .await?;
        Ok(())
    }

    pub async fn heartbeat(&mut self, node_id: &str, updates: &serde_json::Value) -> Result<()> {
        let Some(mut node) = self.get_node(node_id).await? else {
            return Ok(());
        };
        if let Some(obj) = updates.as_object() {
            for (k, v) in obj {
                if k.as_str() == "last_heartbeat" {
                    if let Some(s) = v.as_str() {
                        node.last_heartbeat = s.to_string();
                    }
                }
            }
        }
        let json = node.to_json()?;
        self.redis
            .hset::<_, _, _, ()>(&self.key, node_id, json)
            .await?;
        self.redis
            .expire::<_, ()>(&self.key, REGISTRY_TTL as i64)
            .await?;
        Ok(())
    }

    pub async fn deregister(&mut self, node_id: &str) -> Result<()> {
        self.redis.hdel::<_, _, ()>(&self.key, node_id).await?;
        Ok(())
    }

    pub async fn get_all(&mut self) -> Result<Vec<NodeInfo>> {
        let raw: std::collections::HashMap<String, String> = self.redis.hgetall(&self.key).await?;
        let mut out = Vec::with_capacity(raw.len());
        for (_k, v) in raw {
            if let Ok(node) = NodeInfo::from_json(&v) {
                out.push(node);
            }
        }
        Ok(out)
    }

    pub async fn get_node(&mut self, node_id: &str) -> Result<Option<NodeInfo>> {
        let raw: Option<String> = self.redis.hget(&self.key, node_id).await?;
        match raw {
            Some(s) => Ok(Some(NodeInfo::from_json(&s)?)),
            None => Ok(None),
        }
    }

    pub async fn get_workers(&mut self) -> Result<Vec<NodeInfo>> {
        let all = self.get_all().await?;
        Ok(all
            .into_iter()
            .filter(|n| {
                matches!(
                    n.role,
                    crate::types::NodeRole::Worker | crate::types::NodeRole::Hybrid
                )
            })
            .collect())
    }

    pub async fn get_controllers(&mut self) -> Result<Vec<NodeInfo>> {
        let all = self.get_all().await?;
        Ok(all
            .into_iter()
            .filter(|n| {
                matches!(
                    n.role,
                    crate::types::NodeRole::Controller | crate::types::NodeRole::Hybrid
                )
            })
            .collect())
    }
}
