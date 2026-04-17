use devsper_core::{LlmProvider, LlmRequest, LlmResponse, LlmRole, StopReason};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

/// LM Studio local model provider — OpenAI-compatible API.
/// Expects model names prefixed with "lmstudio:" (e.g. "lmstudio:qwen2.5-coder-7b").
/// Default endpoint: http://localhost:1234
pub struct LmStudioProvider {
    client: Client,
    base_url: String,
    api_key: String,
}

impl LmStudioProvider {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            base_url: "http://localhost:1234".to_string(),
            api_key: String::new(),
        }
    }

    pub fn with_base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    pub fn with_api_key(mut self, key: impl Into<String>) -> Self {
        self.api_key = key.into();
        self
    }
}

impl Default for LmStudioProvider {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Serialize)]
struct OaiRequest<'a> {
    model: &'a str,
    messages: Vec<OaiMessage<'a>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
}

#[derive(Serialize)]
struct OaiMessage<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Deserialize)]
struct OaiResponse {
    choices: Vec<OaiChoice>,
    usage: OaiUsage,
    model: String,
}

#[derive(Deserialize)]
struct OaiChoice {
    message: OaiChoiceMessage,
    finish_reason: Option<String>,
}

#[derive(Deserialize)]
struct OaiChoiceMessage {
    content: Option<String>,
}

#[derive(Deserialize)]
struct OaiUsage {
    prompt_tokens: u32,
    completion_tokens: u32,
}

fn role_str(role: &LlmRole) -> &'static str {
    match role {
        LlmRole::System => "system",
        LlmRole::User | LlmRole::Tool => "user",
        LlmRole::Assistant => "assistant",
    }
}

#[async_trait]
impl LlmProvider for LmStudioProvider {
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse> {
        use tracing::Instrument;

        let span = tracing::info_span!(
            "gen_ai.chat",
            "gen_ai.system" = self.name(),
            "gen_ai.operation.name" = "chat",
            "gen_ai.request.model" = req.model.as_str(),
            "gen_ai.request.max_tokens" = req.max_tokens,
            "gen_ai.response.model" = tracing::field::Empty,
            "gen_ai.usage.input_tokens" = tracing::field::Empty,
            "gen_ai.usage.output_tokens" = tracing::field::Empty,
        );

        // Strip "lmstudio:" prefix before sending
        let model = req.model.strip_prefix("lmstudio:").unwrap_or(&req.model);

        let messages: Vec<OaiMessage> = req
            .messages
            .iter()
            .map(|m| OaiMessage {
                role: role_str(&m.role),
                content: &m.content,
            })
            .collect();

        let body = OaiRequest {
            model,
            messages,
            max_tokens: req.max_tokens,
            temperature: req.temperature,
        };

        debug!(model = %model, provider = "lmstudio", "LM Studio request");

        let result = async {
            let mut request = self
                .client
                .post(format!("{}/v1/chat/completions", self.base_url))
                .header("Content-Type", "application/json");

            if !self.api_key.is_empty() {
                request = request.header("Authorization", format!("Bearer {}", self.api_key));
            }

            let resp = request.json(&body).send().await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                return Err(anyhow!("LM Studio API error {status}: {text}"));
            }

            let data: OaiResponse = resp.json().await?;
            let choice = data
                .choices
                .into_iter()
                .next()
                .ok_or_else(|| anyhow!("No choices in response"))?;

            let stop_reason = match choice.finish_reason.as_deref() {
                Some("tool_calls") => StopReason::ToolUse,
                Some("length") => StopReason::MaxTokens,
                Some("stop") | None => StopReason::EndTurn,
                _ => StopReason::EndTurn,
            };

            Ok(LlmResponse {
                content: choice.message.content.unwrap_or_default(),
                tool_calls: vec![],
                input_tokens: data.usage.prompt_tokens,
                output_tokens: data.usage.completion_tokens,
                model: data.model,
                stop_reason,
            })
        }
        .instrument(span.clone())
        .await;

        if let Ok(ref resp) = result {
            span.record("gen_ai.response.model", resp.model.as_str());
            span.record("gen_ai.usage.input_tokens", resp.input_tokens);
            span.record("gen_ai.usage.output_tokens", resp.output_tokens);
        }
        result
    }

    fn name(&self) -> &str {
        "lmstudio"
    }

    fn supports_model(&self, model: &str) -> bool {
        model.starts_with("lmstudio:")
    }
}
