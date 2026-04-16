use devsper_core::{MemoryStore, MemoryHit};
use anyhow::Result;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::debug;

/// A stored memory entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryEntry {
    pub key: String,
    pub value: serde_json::Value,
    pub namespace: String,
    pub created_at: u64,
    pub tags: Vec<String>,
}

/// In-memory store backed by a HashMap (no SQLite dep needed for initial impl).
/// Replace with SQLite in production via the same trait.
pub struct LocalMemoryStore {
    /// namespace → key → entry
    data: Arc<RwLock<HashMap<String, HashMap<String, MemoryEntry>>>>,
}

impl LocalMemoryStore {
    pub fn new() -> Self {
        Self {
            data: Arc::new(RwLock::new(HashMap::new())),
        }
    }
}

impl Default for LocalMemoryStore {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl MemoryStore for LocalMemoryStore {
    async fn store(&self, namespace: &str, key: &str, value: serde_json::Value) -> Result<()> {
        debug!(namespace = %namespace, key = %key, "Memory store");
        let entry = MemoryEntry {
            key: key.to_string(),
            value,
            namespace: namespace.to_string(),
            created_at: devsper_core::now_ms(),
            tags: vec![],
        };
        let mut data = self.data.write().await;
        data.entry(namespace.to_string())
            .or_insert_with(HashMap::new)
            .insert(key.to_string(), entry);
        Ok(())
    }

    async fn retrieve(&self, namespace: &str, key: &str) -> Result<Option<serde_json::Value>> {
        let data = self.data.read().await;
        Ok(data
            .get(namespace)
            .and_then(|ns| ns.get(key))
            .map(|e| e.value.clone()))
    }

    async fn search(&self, namespace: &str, query: &str, top_k: usize) -> Result<Vec<MemoryHit>> {
        // Simple text matching (BM25-lite): score by query term overlap
        let data = self.data.read().await;
        let ns_data = match data.get(namespace) {
            Some(d) => d,
            None => return Ok(vec![]),
        };

        let query_terms: Vec<String> = query
            .to_lowercase()
            .split_whitespace()
            .map(str::to_string)
            .collect();

        let mut hits: Vec<MemoryHit> = ns_data
            .values()
            .map(|entry| {
                let text = entry.value.to_string().to_lowercase();
                let score = query_terms.iter().filter(|t| text.contains(t.as_str())).count()
                    as f32
                    / query_terms.len().max(1) as f32;
                MemoryHit {
                    key: entry.key.clone(),
                    value: entry.value.clone(),
                    score,
                }
            })
            .filter(|h| h.score > 0.0)
            .collect();

        hits.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        hits.truncate(top_k);
        Ok(hits)
    }

    async fn delete(&self, namespace: &str, key: &str) -> Result<()> {
        let mut data = self.data.write().await;
        if let Some(ns) = data.get_mut(namespace) {
            ns.remove(key);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn store_and_retrieve() {
        let store = LocalMemoryStore::new();
        let ns = "run-1/agent-a";
        store
            .store(ns, "fact-1", serde_json::json!({"text": "The sky is blue"}))
            .await
            .unwrap();
        let val = store.retrieve(ns, "fact-1").await.unwrap();
        assert!(val.is_some());
        assert_eq!(val.unwrap()["text"], "The sky is blue");
    }

    #[tokio::test]
    async fn retrieve_missing_returns_none() {
        let store = LocalMemoryStore::new();
        let val = store.retrieve("ns", "missing").await.unwrap();
        assert!(val.is_none());
    }

    #[tokio::test]
    async fn search_returns_relevant_hits() {
        let store = LocalMemoryStore::new();
        let ns = "run-1/agent-a";
        store
            .store(ns, "k1", serde_json::json!({"text": "cats are fluffy animals"}))
            .await
            .unwrap();
        store
            .store(ns, "k2", serde_json::json!({"text": "dogs are loyal pets"}))
            .await
            .unwrap();
        store
            .store(ns, "k3", serde_json::json!({"text": "the weather is nice today"}))
            .await
            .unwrap();

        let hits = store.search(ns, "cats fluffy", 2).await.unwrap();
        assert!(!hits.is_empty());
        assert_eq!(hits[0].key, "k1"); // highest score
    }

    #[tokio::test]
    async fn delete_removes_entry() {
        let store = LocalMemoryStore::new();
        let ns = "ns";
        store
            .store(ns, "key", serde_json::json!("value"))
            .await
            .unwrap();
        store.delete(ns, "key").await.unwrap();
        let val = store.retrieve(ns, "key").await.unwrap();
        assert!(val.is_none());
    }

    #[tokio::test]
    async fn namespace_isolation() {
        let store = LocalMemoryStore::new();
        store
            .store("ns-a", "key", serde_json::json!("a-value"))
            .await
            .unwrap();
        store
            .store("ns-b", "key", serde_json::json!("b-value"))
            .await
            .unwrap();

        let a = store.retrieve("ns-a", "key").await.unwrap().unwrap();
        let b = store.retrieve("ns-b", "key").await.unwrap().unwrap();
        assert_ne!(a, b);
    }
}
