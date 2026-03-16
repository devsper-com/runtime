---
title: Configuration
---

# Configuration

devsper uses a **TOML-based configuration** system with Pydantic validation. Priority order: **env** > **project config** > **user config** > **defaults**.

**Do not put API keys or secrets in TOML.** Use the credential store (OS keychain) or environment variables. TOML is for non-secret settings only (models, workers, paths, feature flags).

## Config locations

1. **Project:** `./devsper.toml` or `./workflow.devsper.toml` (in current or parent directory)
2. **User:** `~/.config/devsper/config.toml`
3. **Legacy:** `.devsper/config.toml` (still supported; mapped into the new schema)

The first existing project file wins (devsper.toml before workflow.devsper.toml before .devsper/config.toml).

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
| `critic_enabled` | bool | true | (v1.7) Run critic after task completion for eligible roles; can request one retry if score < threshold. |
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

## Example: full `devsper.toml`

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
