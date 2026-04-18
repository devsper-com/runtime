use devsper_core::{MemoryHit, MemoryScope, MemoryStore, RunId};
use anyhow::Result;
use std::sync::Arc;

/// Wraps any MemoryStore and enforces namespace isolation by MemoryScope.
///
/// Namespace format:
///   Run      → "run:{run_id}"
///   Context  → "ctx:{run_id}"
///   Workflow → "wf:{workflow_id}"
pub struct ScopedMemoryStore {
    inner: Arc<dyn MemoryStore>,
    namespace: String,
    scope: MemoryScope,
}

impl ScopedMemoryStore {
    pub fn new(
        inner: Arc<dyn MemoryStore>,
        run_id: RunId,
        workflow_id: Option<String>,
        scope: MemoryScope,
    ) -> Self {
        let namespace = match &scope {
            MemoryScope::Run      => format!("run:{}", run_id.0),
            MemoryScope::Context  => format!("ctx:{}", run_id.0),
            MemoryScope::Workflow => format!("wf:{}", workflow_id.as_deref().unwrap_or("default")),
        };
        Self { inner, namespace, scope }
    }

    pub fn scope(&self) -> &MemoryScope { &self.scope }
    pub fn namespace(&self) -> &str { &self.namespace }

    pub async fn store(&self, key: &str, value: serde_json::Value) -> Result<()> {
        self.inner.store(&self.namespace, key, value).await
    }

    pub async fn retrieve(&self, key: &str) -> Result<Option<serde_json::Value>> {
        self.inner.retrieve(&self.namespace, key).await
    }

    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<MemoryHit>> {
        self.inner.search(&self.namespace, query, top_k).await
    }

    pub async fn delete(&self, key: &str) -> Result<()> {
        self.inner.delete(&self.namespace, key).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::LocalMemoryStore;

    #[tokio::test]
    async fn run_scope_namespace_format() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let scoped = ScopedMemoryStore::new(store, run_id.clone(), None, MemoryScope::Run);
        assert!(scoped.namespace().starts_with("run:"));
        assert!(scoped.namespace().contains(&run_id.0));
    }

    #[tokio::test]
    async fn run_scope_store_and_retrieve() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let scoped = ScopedMemoryStore::new(store, run_id.clone(), None, MemoryScope::Run);
        scoped.store("key", serde_json::json!("value")).await.unwrap();
        let val = scoped.retrieve("key").await.unwrap();
        assert_eq!(val.unwrap(), "value");
    }

    #[tokio::test]
    async fn different_scopes_are_isolated() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let run_scoped = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Run);
        let ctx_scoped = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Context);

        run_scoped.store("key", serde_json::json!("run-value")).await.unwrap();
        let from_ctx = ctx_scoped.retrieve("key").await.unwrap();
        assert!(from_ctx.is_none(), "Context scope must not see Run scope data");
    }

    #[tokio::test]
    async fn workflow_scope_uses_workflow_id() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let wf = ScopedMemoryStore::new(store, run_id, Some("wf-abc".to_string()), MemoryScope::Workflow);
        assert_eq!(wf.namespace(), "wf:wf-abc");
    }

    #[tokio::test]
    async fn workflow_scope_shared_across_runs() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_a = RunId::new();
        let run_b = RunId::new();
        let wf_a = ScopedMemoryStore::new(store.clone(), run_a, Some("shared-wf".to_string()), MemoryScope::Workflow);
        let wf_b = ScopedMemoryStore::new(store.clone(), run_b, Some("shared-wf".to_string()), MemoryScope::Workflow);

        wf_a.store("fact", serde_json::json!("from-run-a")).await.unwrap();
        let seen_by_b = wf_b.retrieve("fact").await.unwrap();
        assert_eq!(seen_by_b.unwrap(), "from-run-a");
    }

    #[tokio::test]
    async fn delete_removes_entry() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let scoped = ScopedMemoryStore::new(store, run_id, None, MemoryScope::Run);
        scoped.store("k", serde_json::json!("v")).await.unwrap();
        scoped.delete("k").await.unwrap();
        assert!(scoped.retrieve("k").await.unwrap().is_none());
    }
}
