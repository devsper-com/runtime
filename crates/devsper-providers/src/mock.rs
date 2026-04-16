use devsper_core::{LlmProvider, LlmRequest, LlmResponse, StopReason};
use anyhow::Result;
use async_trait::async_trait;

/// Mock provider for tests — returns canned responses without HTTP calls.
pub struct MockProvider {
    pub response: String,
}

impl MockProvider {
    pub fn new(response: impl Into<String>) -> Self {
        Self {
            response: response.into(),
        }
    }
}

#[async_trait]
impl LlmProvider for MockProvider {
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse> {
        Ok(LlmResponse {
            content: self.response.clone(),
            tool_calls: vec![],
            input_tokens: req
                .messages
                .iter()
                .map(|m| m.content.len() as u32 / 4)
                .sum(),
            output_tokens: self.response.len() as u32 / 4,
            model: req.model.clone(),
            stop_reason: StopReason::EndTurn,
        })
    }

    fn name(&self) -> &str {
        "mock"
    }

    fn supports_model(&self, model: &str) -> bool {
        model.starts_with("mock")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{LlmMessage, LlmRole};

    #[tokio::test]
    async fn mock_returns_canned_response() {
        let p = MockProvider::new("hello world");
        let req = LlmRequest {
            model: "mock".to_string(),
            messages: vec![LlmMessage {
                role: LlmRole::User,
                content: "hi".to_string(),
            }],
            tools: vec![],
            max_tokens: None,
            temperature: None,
            system: None,
        };
        let res = p.generate(req).await.unwrap();
        assert_eq!(res.content, "hello world");
        assert_eq!(res.model, "mock");
    }
}
