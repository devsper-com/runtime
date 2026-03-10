# Providers

## Provider Routing

Hivemind uses a **provider router** to map **model names** to the correct LLM provider. The agent and planner call `generate(model_name, prompt)`; the router selects the provider and the provider performs the API call.

**Model selection:** Configure `worker` and `planner` in `[models]` (or legacy `worker_model` / `planner_model`) in config or environment (e.g. `HIVEMIND_WORKER_MODEL`, `HIVEMIND_PLANNER_MODEL`). The router infers the vendor from the model name (e.g. `gpt-*` → OpenAI, `claude-*` → Anthropic, `gemini-*` → Google).

## Automatic model routing

You can set **`planner = "auto"`** and **`worker = "auto"`** in `[models]`. The router then selects a model based on task type:

- **Planner** — Prefers higher-quality models for planning and DAG generation.
- **Worker** — Balances cost, latency, and quality for task execution.

This avoids hard-coding model names while keeping runs predictable. You still need at least one provider configured: set API keys via **environment variables** or the **credential store** (`hivemind credentials set ...` or `hivemind credentials migrate`). See [Configuration](configuration#credentials-api-keys).

## Model Spec Format

You can think of model selection as **provider + model**:

| Spec | Provider | Example model |
|------|----------|----------------|
| **openai:model** | OpenAI | `openai:gpt-4o`, `openai:gpt-4o-mini` |
| **anthropic:model** | Anthropic | `anthropic:claude-sonnet`, `anthropic:claude-3-haiku-20240307` |
| **azure:model** | Azure OpenAI | `azure:gpt-4o` (deployment name) |
| **gemini:model** | Google | `gemini:gemini-2.5-pro`, `gemini:gemini-1.5-flash` |
| **github:model** | GitHub Models (Copilot) | `github:gpt-4o`, `github:claude-3.5-sonnet`, `github:phi-3` |

In practice, the code uses the **model name** (e.g. `gpt-4o`, `claude-3-haiku-20240307`, `gemini-1.5-flash`). The router decides the provider from the name prefix:

- `gpt*`, `o1*`, `o3*`, `o4*` → OpenAI (or Azure OpenAI when Azure env is set)
- `claude*` → Anthropic (or Azure Anthropic when Azure Anthropic env is set)
- `gemini*` → Gemini

So you configure models like:

- `gpt-4o` — OpenAI or Azure OpenAI depending on env
- `claude-sonnet` — Anthropic or Azure Anthropic depending on env
- `gemini-2.5-pro` — Google Gemini

**Examples:**

- `openai:gpt-4o` → use OpenAI’s `gpt-4o`
- `anthropic:claude-sonnet` → use Anthropic’s Claude Sonnet
- `azure:gpt-4o` → use Azure OpenAI deployment named `gpt-4o`
- `gemini:gemini-2.5-pro` → use Google’s Gemini 2.5 Pro

(If your codebase uses a literal `provider:model` string, the router can be extended to parse it; otherwise you set the model name and the router infers the provider.)

## GitHub Models (Copilot)

Hivemind can use **GitHub Models** (Copilot API) as a provider. Set **`GITHUB_TOKEN`** in the environment (or in config) and use the **`github:model`** spec:

- **Examples:** `github:gpt-4o`, `github:claude-3.5-sonnet`, `github:phi-3`
- The router maps these to the GitHub Models API; model names follow the same conventions as other providers.
- Useful when you want to run agents via GitHub’s model endpoints without separate OpenAI/Anthropic keys.

## Azure Deployment Support

- **Azure OpenAI:** Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and optionally `AZURE_OPENAI_DEPLOYMENT_NAME` (and `AZURE_OPENAI_API_VERSION` if needed). When these are set, GPT-style model names are served by Azure OpenAI; the deployment name typically matches the model name (e.g. `gpt-4o`, `gpt-5-mini`).
- **Azure Anthropic (e.g. Azure AI Foundry):** Set `AZURE_ANTHROPIC_ENDPOINT` (or `AZURE_ANTHROPIC_API_KEY`) and `AZURE_ANTHROPIC_DEPLOYMENT_NAME`. When set, Claude-style model names use Azure Anthropic.

**Where to set credentials:**

- **Credential store (recommended):** `hivemind credentials set azure api_key`, etc. Keys are stored in the OS keychain and injected into the environment when config is resolved. Use `hivemind credentials export azure` to print env-style lines.
- **Environment variables:** Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, etc., in your shell or `.env`.
- **TOML (not recommended for secrets):** You can still put non-secret values (e.g. `endpoint`, `deployment`) in `[providers.azure]` in `~/.config/hivemind/config.toml` or project TOML; they are applied to the environment when not already set. Prefer the credential store or env for API keys.

See [Configuration](configuration#credentials-api-keys) and [CLI](cli#credentials).
