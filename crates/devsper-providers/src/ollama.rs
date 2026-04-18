use devsper_core::{LlmProvider, LlmRequest, LlmResponse, LlmRole, StopReason};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

/// Ollama local model provider.
pub struct OllamaProvider {
    client: Client,
    base_url: String,
    fallback: bool,
}

impl OllamaProvider {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            base_url: "http://localhost:11434".to_string(),
            fallback: false,
        }
    }

    pub fn with_base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = url.into();
        self
    }

    /// Accept any model not claimed by other providers.
    pub fn as_fallback(mut self) -> Self {
        self.fallback = true;
        self
    }
}

impl Default for OllamaProvider {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Serialize)]
struct OllamaRequest<'a> {
    model: &'a str,
    prompt: String,
    stream: bool,
}

#[derive(Deserialize)]
struct OllamaResponse {
    response: String,
    #[serde(default)]
    prompt_eval_count: u32,
    #[serde(default)]
    eval_count: u32,
}

#[async_trait]
impl LlmProvider for OllamaProvider {
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

        // Flatten messages into a single prompt for Ollama
        let prompt = req
            .messages
            .iter()
            .map(|m| match m.role {
                LlmRole::System => format!("System: {}\n", m.content),
                LlmRole::User | LlmRole::Tool => format!("User: {}\n", m.content),
                LlmRole::Assistant => format!("Assistant: {}\n", m.content),
            })
            .collect::<String>();

        // Strip "ollama:" prefix if present
        let model = req.model.strip_prefix("ollama:").unwrap_or(&req.model);

        debug!(model = %model, "Ollama request");

        let body = OllamaRequest {
            model,
            prompt,
            stream: false,
        };

        let model_name = req.model.clone();
        let result = async {
            let resp = self
                .client
                .post(format!("{}/api/generate", self.base_url))
                .json(&body)
                .send()
                .await?;

            if !resp.status().is_success() {
                let status = resp.status();
                let text = resp.text().await.unwrap_or_default();
                return Err(anyhow!("Ollama error {status}: {text}"));
            }

            let data: OllamaResponse = resp.json().await?;

            Ok(LlmResponse {
                content: data.response,
                tool_calls: vec![],
                input_tokens: data.prompt_eval_count,
                output_tokens: data.eval_count,
                model: model_name,
                stop_reason: StopReason::EndTurn,
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
        "ollama"
    }

    fn supports_model(&self, model: &str) -> bool {
        self.fallback || model.starts_with("ollama:")
    }
}
