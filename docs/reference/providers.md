# Providers

devsper routes LLM calls based on the model name prefix. No configuration file needed — set the appropriate API key environment variable and use the model name directly.

---

## Routing table

| Model prefix  | Provider   | Example                   |
|---------------|------------|---------------------------|
| `claude-*`    | Anthropic  | `claude-opus-4-6`         |
| `gpt-*`       | OpenAI     | `gpt-4o`                  |
| `o1-*` `o3-*` | OpenAI     | `o3-mini`                 |
| `ollama:*`    | Ollama     | `ollama:llama3`            |
| `zai:*`       | ZAI        | `zai:glm-4-flash`          |
| `glm-*`       | ZAI        | `glm-4-flash`              |

The router tries each registered provider in order; the first one returning `supports_model() = true` wins.

---

## Anthropic

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

```lua
devsper.workflow({ model = "claude-opus-4-6" })
```

Endpoint: `https://api.anthropic.com/v1/messages`  
Version header: `anthropic-version: 2023-06-01`

---

## OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

```lua
devsper.workflow({ model = "gpt-4o" })
```

Endpoint: `https://api.openai.com/v1/chat/completions`

---

## Ollama (local)

```bash
export OLLAMA_BASE_URL=http://localhost:11434   # default
```

```lua
devsper.workflow({ model = "ollama:llama3" })
```

Ollama must be running locally. Pull models with `ollama pull llama3`.

---

## ZAI

```bash
export ZAI_API_KEY=...
```

```lua
devsper.workflow({ model = "zai:glm-4-flash" })
-- or
devsper.workflow({ model = "glm-4-flash" })
```

Uses OpenAI-compatible API at `https://api.zai.ai`.

---

## MockProvider

Used in tests. Activated when model name is `"mock"`.

```lua
devsper.workflow({ model = "mock" })
```

Returns a deterministic echo response. No API key required.

---

## Custom base URLs

Override any provider's base URL:

```bash
ANTHROPIC_BASE_URL=https://my-proxy.internal/anthropic
OPENAI_BASE_URL=https://my-proxy.internal/openai
```

---

## Streaming

All providers implement the streaming interface. The executor uses streaming for token-level progress in the TUI. Tool calls are buffered and dispatched after the full response is assembled.

---

## Adding a provider

Implement the `LlmProvider` trait in `crates/devsper-providers/src/`:

```rust
#[async_trait]
pub trait LlmProvider: Send + Sync {
    fn name(&self) -> &str;
    fn supports_model(&self, model: &str) -> bool;
    async fn generate(&self, req: LlmRequest) -> Result<LlmResponse>;
}
```

Register in `ModelRouter::default()` in `crates/devsper-providers/src/router.rs`.
