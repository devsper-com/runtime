use crate::{index::EmbeddingIndex, store::LocalMemoryStore};
use anyhow::Result;
use devsper_core::{MemoryHit, MemoryStore};
use std::sync::Arc;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RetrievalStrategy {
    /// Keyword/BM25 matching (fast, no embeddings)
    Bm25,
    /// TF-IDF embedding similarity (slightly slower)
    Semantic,
    /// Both, merge and re-rank by score
    Hybrid,
}

/// Routes memory retrieval to appropriate strategy
pub struct MemoryRouter {
    store: Arc<dyn MemoryStore>,
    index: Arc<EmbeddingIndex>,
    strategy: RetrievalStrategy,
}

impl MemoryRouter {
    /// Create a router backed by the local in-memory store.
    pub fn local(strategy: RetrievalStrategy) -> Self {
        Self {
            store: Arc::new(LocalMemoryStore::new()),
            index: Arc::new(EmbeddingIndex::new()),
            strategy,
        }
    }

    /// Create a router backed by an external `MemoryStore` implementation.
    pub fn with_external(store: Arc<dyn MemoryStore>, strategy: RetrievalStrategy) -> Self {
        Self {
            store,
            index: Arc::new(EmbeddingIndex::new()),
            strategy,
        }
    }

    /// Deprecated: use `local()` instead. Kept for backward compatibility.
    #[deprecated(note = "Use `local()` instead")]
    pub fn new(strategy: RetrievalStrategy) -> Self {
        Self::local(strategy)
    }

    /// Returns a reference to the underlying store as a dyn MemoryStore trait object.
    pub fn store_ref(&self) -> &Arc<dyn MemoryStore> {
        &self.store
    }

    #[deprecated(note = "Use store_ref() instead")]
    pub fn store(&self) -> &Arc<dyn MemoryStore> {
        &self.store
    }

    /// Store and index a memory fact
    pub async fn remember(
        &self,
        namespace: &str,
        key: &str,
        value: serde_json::Value,
    ) -> Result<()> {
        let text = value.to_string();
        self.store.store(namespace, key, value).await?;
        self.index.index(format!("{namespace}/{key}"), &text).await;
        Ok(())
    }

    /// Retrieve relevant memories for a query
    pub async fn recall(
        &self,
        namespace: &str,
        query: &str,
        top_k: usize,
    ) -> Result<Vec<MemoryHit>> {
        match &self.strategy {
            RetrievalStrategy::Bm25 => self.store.search(namespace, query, top_k).await,
            RetrievalStrategy::Semantic => {
                let results = self.index.search(query, top_k * 2).await;
                let ns_prefix = format!("{namespace}/");
                let mut hits = Vec::new();
                for (doc_id, score) in results {
                    if let Some(key) = doc_id.strip_prefix(&ns_prefix) {
                        if let Ok(Some(value)) = self.store.retrieve(namespace, key).await {
                            hits.push(MemoryHit {
                                key: key.to_string(),
                                value,
                                score,
                            });
                        }
                    }
                }
                hits.truncate(top_k);
                Ok(hits)
            }
            RetrievalStrategy::Hybrid => {
                let mut bm25 = self.store.search(namespace, query, top_k).await?;
                let sem_results = self.index.search(query, top_k).await;
                let ns_prefix = format!("{namespace}/");
                for (doc_id, score) in sem_results {
                    if let Some(key) = doc_id.strip_prefix(&ns_prefix) {
                        let already = bm25.iter().any(|h| h.key == key);
                        if !already {
                            if let Ok(Some(value)) = self.store.retrieve(namespace, key).await {
                                bm25.push(MemoryHit {
                                    key: key.to_string(),
                                    value,
                                    score,
                                });
                            }
                        }
                    }
                }
                bm25.sort_by(|a, b| {
                    b.score
                        .partial_cmp(&a.score)
                        .unwrap_or(std::cmp::Ordering::Equal)
                });
                bm25.truncate(top_k);
                Ok(bm25)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn bm25_recall() {
        let router = MemoryRouter::local(RetrievalStrategy::Bm25);
        router
            .remember("ns", "k1", serde_json::json!("cats are fluffy"))
            .await
            .unwrap();
        router
            .remember("ns", "k2", serde_json::json!("dogs bark"))
            .await
            .unwrap();

        let hits = router.recall("ns", "fluffy cats", 5).await.unwrap();
        assert!(!hits.is_empty());
        assert_eq!(hits[0].key, "k1");
    }

    #[tokio::test]
    async fn semantic_recall() {
        let router = MemoryRouter::local(RetrievalStrategy::Semantic);
        router
            .remember(
                "ns",
                "k1",
                serde_json::json!("machine learning model training"),
            )
            .await
            .unwrap();
        router
            .remember("ns", "k2", serde_json::json!("database query optimization"))
            .await
            .unwrap();

        let hits = router.recall("ns", "machine learning", 5).await.unwrap();
        assert!(!hits.is_empty());
        assert_eq!(hits[0].key, "k1");
    }

    #[tokio::test]
    async fn hybrid_recall() {
        let router = MemoryRouter::local(RetrievalStrategy::Hybrid);
        router
            .remember("ns", "k1", serde_json::json!("rust programming language"))
            .await
            .unwrap();
        router
            .remember("ns", "k2", serde_json::json!("python scripting language"))
            .await
            .unwrap();

        let hits = router.recall("ns", "rust language", 5).await.unwrap();
        assert!(!hits.is_empty());
    }

    #[tokio::test]
    async fn with_external_delegates_to_store() {
        use std::sync::atomic::{AtomicUsize, Ordering};

        let call_count = Arc::new(AtomicUsize::new(0));
        let count_clone = call_count.clone();

        // A minimal mock MemoryStore
        struct MockStore {
            count: Arc<AtomicUsize>,
        }

        #[async_trait::async_trait]
        impl MemoryStore for MockStore {
            async fn store(&self, _ns: &str, _key: &str, _value: serde_json::Value) -> Result<()> {
                self.count.fetch_add(1, Ordering::SeqCst);
                Ok(())
            }
            async fn retrieve(&self, _ns: &str, _key: &str) -> Result<Option<serde_json::Value>> {
                Ok(None)
            }
            async fn search(
                &self,
                _ns: &str,
                _query: &str,
                _top_k: usize,
            ) -> Result<Vec<MemoryHit>> {
                Ok(vec![])
            }
            async fn delete(&self, _ns: &str, _key: &str) -> Result<()> {
                Ok(())
            }
        }

        let mock = Arc::new(MockStore { count: count_clone });
        let router =
            MemoryRouter::with_external(mock as Arc<dyn MemoryStore>, RetrievalStrategy::Bm25);

        router
            .remember("ns", "k1", serde_json::json!("test value"))
            .await
            .unwrap();
        assert_eq!(call_count.load(Ordering::SeqCst), 1);

        // BM25 recall should delegate to the external store's search
        let hits = router.recall("ns", "test", 5).await.unwrap();
        assert!(hits.is_empty()); // mock returns empty
    }
}
