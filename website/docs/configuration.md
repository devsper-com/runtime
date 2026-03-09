# Configuration

Hivemind uses a **TOML-based configuration** system with Pydantic validation. Priority order: **env** > **project config** > **user config** > **defaults**.

**Do not put API keys or secrets in TOML.** Use the [credential store](#credentials-api-keys) (OS keychain) or environment variables. TOML is for non-secret settings only (models, workers, paths, feature flags).

## Config locations

1. **Project:** `./hivemind.toml` or `./workflow.hivemind.toml` (in current or parent directory)
2. **User:** `~/.config/hivemind/config.toml`
3. **Legacy:** `.hivemind/config.toml` (still supported; mapped into the new schema)

The first existing project file wins (hivemind.toml before workflow.hivemind.toml before .hivemind/config.toml).

## Schema (v1 format)

### `[swarm]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `workers` | int | 4 | Max concurrent tasks (worker pool size). |
| `adaptive_planning` | bool | false | Whether to expand the DAG after task completion. |
| `max_iterations` | int | 10 | Upper bound on planning/expansion. |
| `speculative_execution` | bool | false | Allow speculative execution of tasks with one running dependency. |
| `cache_enabled` | bool | false | Enable task result cache (exact and optionally semantic). |
| `parallel_tools` | bool | true | (v1.6) Run independent tool calls in parallel within an agent turn. |
| `critic_enabled` | bool | true | (v1.7) Run critic after task completion for eligible roles; can request one retry if score &lt; threshold. |
| `critic_threshold` | float | 0.70 | (v1.7) Score below this may trigger a retry when the critic requests it. |
| `critic_roles` | list[string] | ["research", "analysis", "code"] | (v1.7) Task roles eligible for critique. |
| `message_bus_enabled` | bool | true | (v1.7) Per-run message bus so agents can broadcast discoveries and receive shared context. |
| `prefetch_enabled` | bool | true | (v1.7) Pre-warm memory and tool selection for speculative successor tasks. |
| `prefetch_max_age_seconds` | float | 30 | (v1.7) Prefetched result older than this is discarded when the task starts. |

### `[models]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `planner` | string | (inferred) | Model for the planner (e.g. `azure:gpt-4o`, `gpt-4o-mini`, or `"auto"`). |
| `worker` | string | (inferred) | Model for agents (e.g. `azure:gpt-4o`, `gpt-4o-mini`, or `"auto"`). |
| `fast` | string | (none) | (v1.6) Model for **simple** tasks (e.g. haiku/flash). Used when complexity routing is enabled. |
| `quality` | string | (planner) | (v1.6) Model for **complex** tasks. Defaults to planner when not set. |

Model names are passed to the provider router; use the same format as env (e.g. `gpt-4o`, or `azure:gpt-4o` if using Azure). Use **`"auto"`** for automatic model routing: the router picks a model by task type (planning vs execution) for cost/latency/quality balance. See [Providers](providers#automatic-model-routing). With **complexity routing** (v1.6), simple tasks use `fast`, medium use `worker`, and complex use `quality`.

### `[cache]` (v1.6)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | true | Enable cache when swarm has `cache_enabled`. |
| `semantic` | bool | false | Use embedding-based similarity lookup instead of exact match only. |
| `similarity_threshold` | float | 0.92 | Min cosine similarity for a cache hit (tune per project). |
| `max_age_hours` | float | 168 | Expire entries after this many hours (default 1 week). |

### `[memory]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | true | Whether memory is used. |
| `store_results` | bool | true | Whether to store swarm results into memory. |
| `top_k` | int | 5 | Number of memories to inject into the agent context. |

### `[tools]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | list[string] | (all) | Categories to allow (e.g. `["research", "coding", "documents"]`). Omit or empty = all. |
| `top_k` | int | 0 | Max tools per task by similarity (0 = no limit, use all). |

When `top_k` > 0, the **smart tool selector** embeds the task and each tool, then passes only the top-k most relevant tools to the agent.

### `[telemetry]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | true | Whether telemetry is enabled. |
| `save_events` | bool | true | Whether to persist events to JSONL. |

### `[providers.azure]`

| Key | Type | Description |
|-----|------|-------------|
| `endpoint` | string | Azure OpenAI/Anthropic endpoint URL. |
| `deployment` | string | Deployment name. |
| `api_key` | string | (Optional) API key (can use env instead). |
| `api_version` | string | (Optional) API version. |

Values are applied to `os.environ` when not already set, so existing provider code works without code changes.

### Top-level (legacy / overrides)

- `events_dir` — Directory for event log files (e.g. `.hivemind/events`).
- `data_dir` — Base directory for data (e.g. `.hivemind`); memory store path is derived from this.

## Credentials (API keys)

API keys and secrets are **not** stored in config files. They are managed in one of two ways:

1. **Credential store (recommended)** — OS keychain via the `hivemind credentials` CLI. Stored keys are injected into the environment when config is resolved, so all providers (OpenAI, Anthropic, Azure, GitHub, Gemini) work without code changes.
2. **Environment variables** — Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, etc., in your shell or `.env` (loaded by the CLI before commands run).

**CLI commands:**

- `hivemind credentials set <provider> <key>` — Store a value (prompts; uses keyring).
- `hivemind credentials list` — List stored entries (no values shown).
- `hivemind credentials migrate` — Copy credentials from `.env` / TOML into the keyring.
- `hivemind credentials export <provider>` — Print `KEY=value` lines for that provider (e.g. for `eval` or `.env`).
- `hivemind credentials delete <provider> <key>` — Remove a credential.

**Supported providers:** `openai`, `anthropic`, `github`, `gemini`, `azure`, `azure_anthropic`. Keys vary (e.g. `api_key`, `token`, `endpoint`, `deployment`, `api_version`). See [CLI](cli#credentials) for full usage.

**Resolution:** When `resolve_config()` runs (e.g. at the start of `run`, `tui`, or `get_config()`), credentials from the keyring are injected into `os.environ` for any provider/key not already set. So existing code that reads `os.environ["OPENAI_API_KEY"]` (or similar) continues to work.

## Environment overrides

These override any TOML value:

- `HIVEMIND_WORKER_MODEL` — Same as `[models] worker`.
- `HIVEMIND_PLANNER_MODEL` — Same as `[models] planner`.
- `HIVEMIND_EVENTS_DIR` — Same as `events_dir`.
- `HIVEMIND_DATA_DIR` — Same as `data_dir`.

Provider keys (e.g. `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`) can be set in the environment or via the credential store; see [Providers](providers).

## Example: full `hivemind.toml`

```toml
[swarm]
workers = 6
adaptive_planning = true
max_iterations = 10

[models]
planner = "azure:gpt-4o"
worker = "azure:gpt-4o"

[memory]
enabled = true
store_results = true
top_k = 5

[tools]
enabled = ["research", "coding", "documents"]
top_k = 12

[telemetry]
enabled = true
save_events = true

[providers.azure]
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
```

## Using config in code

```python
from hivemind import get_config, Swarm

# Load global config (all locations + env)
cfg = get_config()
print(cfg.worker_model, cfg.planner_model)
print(cfg.swarm.workers, cfg.tools.top_k)

# Swarm from config file
swarm = Swarm(config="hivemind.toml")
results = swarm.run("Your task")

# Swarm from config object
swarm = Swarm(config=cfg)
```

## Backward compatibility

- **Legacy paths:** `.hivemind/config.toml` and `~/.config/hivemind/config.toml` are still read. A `[default]` section or top-level keys like `worker_model`, `planner_model`, `events_dir`, `data_dir` are mapped into the new schema.
- **API:** `get_config()` returns an object that still has `worker_model`, `planner_model`, `events_dir`, `data_dir` (as properties or fields), so existing code using these names continues to work.
