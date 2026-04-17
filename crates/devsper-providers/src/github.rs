use devsper_core::{LlmProvider, LlmRequest, LlmResponse, LlmRole, StopReason};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

const BASE_URL: &str = "https://models.github.com/inference/v1";

/// GitHub Models API provider — OpenAI-compatible, Bearer token auth.
/// Expects model names prefixed with "github:" (e.g. "github:gpt-4o").
pub struct GithubModelsProvider {
    client: Client,
    token: String,
}

impl GithubModelsProvider {
    pub fn new(token: impl Into<String>) -> Self {
        Self {
            client: Client::new(),
            token: token.into(),
        }
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
impl LlmProvider for GithubModelsProvider {
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

        // Strip "github:" prefix before sending to API
        let model = req.model.strip_prefix("github:").unwrap_or(&req.model);

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

        debug!(model = %model, provider = "github-models", "GitHub Models request");

        let result = async {
            let resp = self
                .client
                .post(format!("{BASE_URL}/chat/completions"))
                .header("Authorization", format!("Bearer {}", self.token))
                .header("Content-Type", "application/json")
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                return Err(anyhow!("github-models API error {status}: {text}"));
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
        "github-models"
    }

    fn supports_model(&self, model: &str) -> bool {
        model.starts_with("github:")
    }
}
