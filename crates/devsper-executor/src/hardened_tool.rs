use devsper_core::{ToolCall, ToolDef, ToolExecutor, ToolResult};
use anyhow::Result;
use async_trait::async_trait;
use std::sync::Arc;
use tokio::time::{timeout, Duration};
use tracing::warn;

#[derive(Debug, Clone)]
pub struct ToolPolicy {
    pub timeout_ms: u64,
    pub max_retries: u32,
    pub retry_delay_ms: u64,
}

impl Default for ToolPolicy {
    fn default() -> Self {
        Self { timeout_ms: 10_000, max_retries: 2, retry_delay_ms: 200 }
    }
}

pub struct HardenedToolExecutor {
    inner: Arc<dyn ToolExecutor>,
    policy: ToolPolicy,
}

impl HardenedToolExecutor {
    pub fn new(inner: Arc<dyn ToolExecutor>, policy: ToolPolicy) -> Self {
        Self { inner, policy }
    }
}

#[async_trait]
impl ToolExecutor for HardenedToolExecutor {
    async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
        let mut last_err = anyhow::anyhow!("no attempts made");
        for attempt in 0..=self.policy.max_retries {
            if attempt > 0 {
                tokio::time::sleep(Duration::from_millis(self.policy.retry_delay_ms)).await;
                warn!(tool = %call.name, attempt, "retrying tool call");
            }
            let fut = self.inner.execute(call.clone());
            match timeout(Duration::from_millis(self.policy.timeout_ms), fut).await {
                Ok(Ok(result)) => return Ok(result),
                Ok(Err(e)) => last_err = e,
                Err(_) => {
                    last_err = anyhow::anyhow!(
                        "tool '{}' timed out after {}ms",
                        call.name,
                        self.policy.timeout_ms
                    );
                }
            }
        }
        Ok(ToolResult {
            tool_call_id: call.id,
            content: serde_json::json!({ "error": last_err.to_string() }),
            is_error: true,
        })
    }

    fn list_tools(&self) -> Vec<ToolDef> {
        self.inner.list_tools()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{ToolCall, ToolDef, ToolResult};
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn make_call() -> ToolCall {
        ToolCall { id: "tc-1".to_string(), name: "test_tool".to_string(), arguments: serde_json::json!({}) }
    }

    struct SlowTool { delay_ms: u64, call_count: Arc<AtomicUsize> }

    #[async_trait]
    impl ToolExecutor for SlowTool {
        async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            tokio::time::sleep(Duration::from_millis(self.delay_ms)).await;
            Ok(ToolResult { tool_call_id: call.id, content: serde_json::json!("ok"), is_error: false })
        }
        fn list_tools(&self) -> Vec<ToolDef> { vec![] }
    }

    struct FailingTool { call_count: Arc<AtomicUsize> }

    #[async_trait]
    impl ToolExecutor for FailingTool {
        async fn execute(&self, _call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            Err(anyhow::anyhow!("tool error"))
        }
        fn list_tools(&self) -> Vec<ToolDef> { vec![] }
    }

    struct OkTool;

    #[async_trait]
    impl ToolExecutor for OkTool {
        async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
            Ok(ToolResult { tool_call_id: call.id, content: serde_json::json!("done"), is_error: false })
        }
        fn list_tools(&self) -> Vec<ToolDef> { vec![] }
    }

    #[tokio::test]
    async fn timeout_returns_error_result() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(SlowTool { delay_ms: 500, call_count: count });
        let executor = HardenedToolExecutor::new(inner, ToolPolicy { timeout_ms: 50, max_retries: 0, retry_delay_ms: 0 });
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert!(result.content["error"].as_str().unwrap().contains("timed out"));
    }

    #[tokio::test]
    async fn retries_on_failure() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(FailingTool { call_count: count.clone() });
        let executor = HardenedToolExecutor::new(inner, ToolPolicy { timeout_ms: 1000, max_retries: 2, retry_delay_ms: 10 });
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert_eq!(count.load(Ordering::SeqCst), 3, "initial + 2 retries = 3 total");
    }

    #[tokio::test]
    async fn succeeds_on_first_attempt() {
        let executor = HardenedToolExecutor::new(Arc::new(OkTool), ToolPolicy::default());
        let result = executor.execute(make_call()).await.unwrap();
        assert!(!result.is_error);
        assert_eq!(result.content, serde_json::json!("done"));
    }

    #[tokio::test]
    async fn list_tools_delegates_to_inner() {
        struct ToolLister;
        #[async_trait]
        impl ToolExecutor for ToolLister {
            async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
                Ok(ToolResult { tool_call_id: call.id, content: serde_json::json!(null), is_error: false })
            }
            fn list_tools(&self) -> Vec<ToolDef> {
                vec![ToolDef { name: "my_tool".to_string(), description: "does things".to_string(), parameters: serde_json::json!({}) }]
            }
        }
        let executor = HardenedToolExecutor::new(Arc::new(ToolLister), ToolPolicy::default());
        let tools = executor.list_tools();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "my_tool");
    }
}
