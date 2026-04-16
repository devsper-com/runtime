use crate::types::{BusMessage, LlmRequest, LlmResponse, ToolCall, ToolDef, ToolResult};
use anyhow::Result;
use serde_json::Value;

/// A search result from semantic memory
#[derive(Debug, Clone)]
pub struct MemoryHit {
    pub key: String,
    pub value: Value,
    pub score: f32,
}

/// Trait for LLM providers (Anthropic, OpenAI, Ollama, etc.)
#[async_trait::async_trait]
pub trait LlmProvider: Send + Sync {
    /// Generate a response (non-streaming)
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse>;

    /// Provider name for routing/logging
    fn name(&self) -> &str;

    /// Models supported by this provider (prefix matching)
    fn supports_model(&self, model: &str) -> bool;
}

/// Trait for message bus backends
#[async_trait::async_trait]
pub trait Bus: Send + Sync {
    /// Publish a message to a topic
    async fn publish(&self, msg: BusMessage) -> Result<()>;

    /// Subscribe to a topic with a handler
    async fn subscribe(
        &self,
        topic: &str,
        handler: Box<dyn Fn(BusMessage) + Send + Sync>,
    ) -> Result<()>;

    /// Start the bus
    async fn start(&self) -> Result<()>;

    /// Stop the bus
    async fn stop(&self) -> Result<()>;
}

/// Trait for memory storage backends
#[async_trait::async_trait]
pub trait MemoryStore: Send + Sync {
    /// Store a memory fact
    async fn store(&self, namespace: &str, key: &str, value: Value) -> Result<()>;

    /// Retrieve a memory fact
    async fn retrieve(&self, namespace: &str, key: &str) -> Result<Option<Value>>;

    /// Semantic search over stored memories
    async fn search(&self, namespace: &str, query: &str, top_k: usize) -> Result<Vec<MemoryHit>>;

    /// Delete a memory fact
    async fn delete(&self, namespace: &str, key: &str) -> Result<()>;
}

/// Trait for tool executors (Lua plugins, external processes)
#[async_trait::async_trait]
pub trait ToolExecutor: Send + Sync {
    /// Execute a tool call
    async fn execute(&self, call: ToolCall) -> Result<ToolResult>;

    /// List available tools
    fn list_tools(&self) -> Vec<ToolDef>;
}
