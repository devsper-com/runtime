//! AgentRequest / AgentResponse — serialization boundary with Python agent.

use serde::{Deserialize, Serialize};

use crate::types::Task;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentRequest {
    pub task: Task,
    #[serde(default)]
    pub memory_context: String,
    #[serde(default)]
    pub tools: Vec<String>,
    #[serde(default)]
    pub model: String,
    #[serde(default)]
    pub system_prompt: String,
    #[serde(default)]
    pub prefetch_used: bool,
    /// Controller-executed tool protocol: results from previous round.
    #[serde(default)]
    pub tool_results: Option<Vec<serde_json::Value>>,
    /// When true, executor returns tool_calls in response instead of running tools locally.
    #[serde(default)]
    pub distributed_tools: bool,
    #[serde(default)]
    pub budget_remaining_usd: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResponse {
    pub task_id: String,
    #[serde(default)]
    pub result: String,
    #[serde(default)]
    pub tools_called: Vec<String>,
    #[serde(default)]
    pub broadcasts: Vec<String>,
    pub tokens_used: Option<u64>,
    #[serde(default)]
    pub prompt_tokens: Option<u64>,
    #[serde(default)]
    pub completion_tokens: Option<u64>,
    #[serde(default)]
    pub cost_usd: Option<f64>,
    #[serde(default)]
    pub duration_seconds: f64,
    pub error: Option<String>,
    #[serde(default)]
    pub success: bool,
    /// When model requested tool calls (distributed_tools mode), worker sends these to controller.
    #[serde(default)]
    pub tool_calls: Option<Vec<serde_json::Value>>,
}
