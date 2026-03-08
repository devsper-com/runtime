# Providers

## Provider Routing

Hivemind uses a **provider router** to map **model names** to the correct LLM provider. The agent and planner call `generate(model_name, prompt)`; the router selects the provider and the provider performs the API call.

**Model selection:** Configure `worker_model` and `planner_model` in config or environment (e.g. `HIVEMIND_WORKER_MODEL`, `HIVEMIND_PLANNER_MODEL`). The router infers the vendor from the model name (e.g. `gpt-*` → OpenAI, `claude-*` → Anthropic, `gemini-*` → Google).

## Model Spec Format

You can think of model selection as **provider + model**:

| Spec | Provider | Example model |
|------|----------|----------------|
| **openai:model** | OpenAI | `openai:gpt-4o`, `openai:gpt-4o-mini` |
| **anthropic:model** | Anthropic | `anthropic:claude-sonnet`, `anthropic:claude-3-haiku-20240307` |
| **azure:model** | Azure OpenAI | `azure:gpt-4o` (deployment name) |
| **gemini:model** | Google | `gemini:gemini-2.5-pro`, `gemini:gemini-1.5-flash` |

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

## Azure Deployment Support

- **Azure OpenAI:** Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and optionally `AZURE_OPENAI_DEPLOYMENT_NAME` (and `AZURE_OPENAI_API_VERSION` if needed). When these are set, GPT-style model names are served by Azure OpenAI; the deployment name typically matches the model name (e.g. `gpt-4o`, `gpt-5-mini`).
- **Azure Anthropic (e.g. Azure AI Foundry):** Set `AZURE_ANTHROPIC_ENDPOINT` (or `AZURE_ANTHROPIC_API_KEY`) and `AZURE_ANTHROPIC_DEPLOYMENT_NAME`. When set, Claude-style model names use Azure Anthropic.

Configuration can be in **environment variables** or in TOML:

- **User/project TOML:** `~/.config/hivemind/config.toml` or `.hivemind/config.toml` with sections `[azure_openai]` and `[azure_anthropic]` (with `endpoint`, `api_key`, `deployment_name`, etc.). Values are applied to the environment when not already set, so you can run from any directory without a local `.env`.

See **Configuration** in the main README and in the development guide for full TOML examples.
