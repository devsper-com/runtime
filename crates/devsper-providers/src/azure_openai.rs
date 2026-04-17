use devsper_core::{LlmProvider, LlmRequest, LlmResponse, LlmRole, StopReason};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

/// Azure OpenAI provider.
///
/// URL format: `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}`
/// Auth header: `api-key: {api_key}` (NOT Bearer)
/// Supports model names prefixed with "azure:" (e.g. "azure:gpt-4o").
pub struct AzureOpenAiProvider {
    client: Client,
    api_key: String,
    endpoint: String,
    deployment: String,
    api_version: String,
}

impl AzureOpenAiProvider {
    pub fn new(
        api_key: impl Into<String>,
        endpoint: impl Into<String>,
        deployment: impl Into<String>,
        api_version: impl Into<String>,
    ) -> Self {
        Self {
            client: Client::new(),
            api_key: api_key.into(),
            endpoint: endpoint.into(),
            deployment: deployment.into(),
            api_version: api_version.into(),
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
impl LlmProvider for AzureOpenAiProvider {
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

        let url = format!(
            "{}/openai/deployments/{}/chat/completions?api-version={}",
            self.endpoint, self.deployment, self.api_version
        );

        let messages: Vec<OaiMessage> = req
            .messages
            .iter()
            .map(|m| OaiMessage {
                role: role_str(&m.role),
                content: &m.content,
            })
            .collect();

        // The deployment is fixed — use it as the model name in the request body
        let body = OaiRequest {
            model: &self.deployment,
            messages,
            max_tokens: req.max_tokens,
            temperature: req.temperature,
        };

        debug!(deployment = %self.deployment, provider = "azure-openai", "Azure OpenAI request");

        let result = async {
            let resp = self
                .client
                .post(&url)
                .header("api-key", &self.api_key)
                .header("Content-Type", "application/json")
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                return Err(anyhow!("azure-openai API error {status}: {text}"));
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
        "azure-openai"
    }

    fn supports_model(&self, model: &str) -> bool {
        model.starts_with("azure:")
    }
}
