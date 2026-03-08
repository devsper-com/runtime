# Configuration

Hivemind uses a **TOML-based configuration** system with Pydantic validation. Priority order: **env** > **project config** > **user config** > **defaults**.

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

### `[models]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `planner` | string | (inferred) | Model for the planner (e.g. `azure:gpt-4o`, `gpt-4o-mini`, or `"auto"`). |
| `worker` | string | (inferred) | Model for agents (e.g. `azure:gpt-4o`, `gpt-4o-mini`, or `"auto"`). |

Model names are passed to the provider router; use the same format as env (e.g. `gpt-4o`, or `azure:gpt-4o` if using Azure). Use **`"auto"`** for automatic model routing: the router picks a model by task type (planning vs execution) for cost/latency/quality balance. See [Providers](providers.md#automatic-model-routing).

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

## Environment overrides

These override any TOML value:

- `HIVEMIND_WORKER_MODEL` — Same as `[models] worker`.
- `HIVEMIND_PLANNER_MODEL` — Same as `[models] planner`.
- `HIVEMIND_EVENTS_DIR` — Same as `events_dir`.
- `HIVEMIND_DATA_DIR` — Same as `data_dir`.

Provider keys (e.g. `OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`) are unchanged; see [Providers](providers.md).

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
