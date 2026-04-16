use devsper_core::{LlmProvider, LlmRequest, LlmResponse, LlmRole, StopReason};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

/// Anthropic Claude API provider (Messages API).
pub struct AnthropicProvider {
    client: Client,
    api_key: String,
    base_url: String,
}

impl AnthropicProvider {
    pub fn new(api_key: impl Into<String>) -> Self {
        Self {
            client: Client::new(),
            api_key: api_key.into(),
            base_url: "https://api.anthropic.com".to_string(),
        }
    }

    pub fn with_base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }
}

#[derive(Serialize)]
struct AnthropicRequest<'a> {
    model: &'a str,
    messages: Vec<AnthropicMessage<'a>>,
    max_tokens: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    system: Option<&'a str>,
}

#[derive(Serialize)]
struct AnthropicMessage<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicContent>,
    usage: AnthropicUsage,
    model: String,
    stop_reason: Option<String>,
}

#[derive(Deserialize)]
struct AnthropicContent {
    #[serde(rename = "type")]
    content_type: String,
    text: Option<String>,
}

#[derive(Deserialize)]
struct AnthropicUsage {
    input_tokens: u32,
    output_tokens: u32,
}

fn role_to_str(role: &LlmRole) -> &'static str {
    match role {
        LlmRole::User | LlmRole::Tool => "user",
        LlmRole::Assistant => "assistant",
        LlmRole::System => "user", // system goes in separate field
    }
}

#[async_trait]
impl LlmProvider for AnthropicProvider {
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse> {
        let messages: Vec<AnthropicMessage> = req
            .messages
            .iter()
            .filter(|m| !matches!(m.role, LlmRole::System))
            .map(|m| AnthropicMessage {
                role: role_to_str(&m.role),
                content: &m.content,
            })
            .collect();

        let system_from_messages = req
            .messages
            .iter()
            .find(|m| matches!(m.role, LlmRole::System))
            .map(|m| m.content.as_str());

        let system = req.system.as_deref().or(system_from_messages);

        let body = AnthropicRequest {
            model: &req.model,
            messages,
            max_tokens: req.max_tokens.unwrap_or(4096),
            system,
        };

        debug!(model = %req.model, "Anthropic request");

        let resp = self
            .client
            .post(format!("{}/v1/messages", self.base_url))
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow!("Anthropic API error {status}: {text}"));
        }

        let data: AnthropicResponse = resp.json().await?;

        let content = data
            .content
            .iter()
            .filter_map(|c| {
                if c.content_type == "text" {
                    c.text.clone()
                } else {
                    None
                }
            })
            .collect::<Vec<_>>()
            .join("");

        let stop_reason = match data.stop_reason.as_deref() {
            Some("end_turn") => StopReason::EndTurn,
            Some("tool_use") => StopReason::ToolUse,
            Some("max_tokens") => StopReason::MaxTokens,
            _ => StopReason::EndTurn,
        };

        Ok(LlmResponse {
            content,
            tool_calls: vec![],
            input_tokens: data.usage.input_tokens,
            output_tokens: data.usage.output_tokens,
            model: data.model,
            stop_reason,
        })
    }

    fn name(&self) -> &str {
        "anthropic"
    }

    fn supports_model(&self, model: &str) -> bool {
        model.starts_with("claude-")
    }
}
