use devsper_core::{LlmProvider, LlmRequest, LlmResponse};
use anyhow::{anyhow, Result};
use async_trait::async_trait;
use std::sync::Arc;
use tracing::debug;

/// Routes LLM requests to the correct provider based on model prefix.
/// claude-*      → Anthropic
/// gpt-*, o1*, o3* → OpenAI
/// ollama:*      → Ollama
/// zai:*, glm-*  → ZAI
/// mock*         → Mock
pub struct ModelRouter {
    providers: Vec<Arc<dyn LlmProvider>>,
}

impl ModelRouter {
    pub fn new() -> Self {
        Self { providers: vec![] }
    }

    pub fn with_provider(mut self, provider: Arc<dyn LlmProvider>) -> Self {
        self.providers.push(provider);
        self
    }

    pub fn add_provider(&mut self, provider: Arc<dyn LlmProvider>) {
        self.providers.push(provider);
    }

    fn route(&self, model: &str) -> Option<&Arc<dyn LlmProvider>> {
        self.providers.iter().find(|p| p.supports_model(model))
    }
}

impl Default for ModelRouter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl LlmProvider for ModelRouter {
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse> {
        let provider = self
            .route(&req.model)
            .ok_or_else(|| anyhow!("No provider found for model: {}", req.model))?;
        debug!(model = %req.model, provider = %provider.name(), "Routing request");
        provider.generate(req).await
    }

    fn name(&self) -> &str {
        "router"
    }

    fn supports_model(&self, model: &str) -> bool {
        self.route(model).is_some()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mock::MockProvider;
    use devsper_core::{LlmMessage, LlmRole};

    fn make_req(model: &str) -> LlmRequest {
        LlmRequest {
            model: model.to_string(),
            messages: vec![LlmMessage {
                role: LlmRole::User,
                content: "test".to_string(),
            }],
            tools: vec![],
            max_tokens: None,
            temperature: None,
            system: None,
        }
    }

    #[tokio::test]
    async fn routes_to_mock() {
        let router = ModelRouter::new().with_provider(Arc::new(MockProvider::new("mocked")));

        let res = router.generate(make_req("mock")).await.unwrap();
        assert_eq!(res.content, "mocked");
    }

    #[tokio::test]
    async fn unknown_model_returns_error() {
        let router = ModelRouter::new();
        let result = router.generate(make_req("unknown-model")).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn router_supports_model_delegates() {
        let router = ModelRouter::new().with_provider(Arc::new(MockProvider::new("")));
        assert!(router.supports_model("mock"));
        assert!(!router.supports_model("claude-opus-4-6"));
    }
}
