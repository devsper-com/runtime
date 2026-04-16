use anyhow::{anyhow, Result};
use devsper_core::{ToolCall, ToolDef, ToolResult};
use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Type alias for the async executor function stored in each registered tool.
pub type ExecutorFn = Arc<
    dyn Fn(ToolCall) -> Pin<Box<dyn std::future::Future<Output = Result<ToolResult>> + Send>>
        + Send
        + Sync,
>;

/// Registered tool: its definition + an executor function
pub struct RegisteredTool {
    pub def: ToolDef,
    pub executor: ExecutorFn,
}

/// Registry of all tools registered by loaded plugins
pub struct PluginRegistry {
    tools: Arc<RwLock<HashMap<String, RegisteredTool>>>,
}

impl PluginRegistry {
    pub fn new() -> Self {
        Self {
            tools: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub async fn register(&self, tool: RegisteredTool) {
        let name = tool.def.name.clone();
        self.tools.write().await.insert(name, tool);
    }

    pub async fn list(&self) -> Vec<ToolDef> {
        self.tools
            .read()
            .await
            .values()
            .map(|t| t.def.clone())
            .collect()
    }

    pub async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
        let tools = self.tools.read().await;
        let tool = tools
            .get(&call.name)
            .ok_or_else(|| anyhow!("Tool not found: {}", call.name))?;
        (tool.executor)(call).await
    }
}

impl Default for PluginRegistry {
    fn default() -> Self {
        Self::new()
    }
}
