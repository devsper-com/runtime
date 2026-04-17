# devsper-providers

LLM provider adapters and model router for the devsper runtime.

## Providers

| Provider | Model prefix | Env var |
|----------|-------------|---------|
| Anthropic | `claude-*` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-*`, `o1*`, `o3*` | `OPENAI_API_KEY` |
| Ollama | `ollama:*` | `OLLAMA_HOST` (default: `http://localhost:11434`) |
| LM Studio | `lmstudio:*` | `LMSTUDIO_BASE_URL` (default: `http://localhost:1234`) |
| ZAI | `zai:*`, `glm-*` | `ZAI_API_KEY` |
| Mock | `mock*` | — |

## ModelRouter

`ModelRouter` implements `LlmProvider` and dispatches requests to the correct backend by model prefix. Add providers at startup; the router picks the first that `supports_model()` returns true for.

## Usage

```toml
[dependencies]
devsper-providers = "0.1"
```

```rust
use devsper_providers::{ModelRouter, MockProvider};
use devsper_providers::anthropic::AnthropicProvider;
use devsper_core::{LlmProvider, LlmRequest, Message, Role};
use std::sync::Arc;

let router = ModelRouter::new()
    .with_provider(Arc::new(AnthropicProvider::from_env()?))
    .with_provider(Arc::new(MockProvider::new()));

let resp = router.generate(LlmRequest {
    model: "claude-3-5-haiku-20241022".into(),
    messages: vec![Message { role: Role::User, content: "Hello".into() }],
    tools: vec![],
    max_tokens: Some(256),
    temperature: None,
    stream: false,
}).await?;

println!("{}", resp.content);
```

### Mock provider (testing)

```rust
let mock = MockProvider::new(); // always returns "mock response"
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
