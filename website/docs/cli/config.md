---
title: "CLI: config"
---

# hivemind config

Hivemind uses TOML-based configuration files to control swarm behavior, model selection, memory, tools, caching, and more.

## Config File Locations

Hivemind loads configuration from multiple sources, merged in priority order (highest first):

1. **Environment variables** — `HIVEMIND_*` overrides
2. **Project config** — `./hivemind.toml` in the current directory
3. **User config** — `~/.config/hivemind/config.toml`
4. **Defaults** — built-in defaults shipped with the package

A project config is created automatically when you run `hivemind init`.

## Creating a Config

```bash
hivemind init
```

This generates a `hivemind.toml` in the current directory with sensible defaults. Edit it to match your project's needs.

## Schema Reference

### [swarm]

Controls the core swarm runtime.

```toml
[swarm]
worker_model = "gpt-4o"
planner_model = "gpt-4o"
max_workers = 4
events_dir = ".hivemind/events"
timeout = 300
```

### [models]

Define named model configurations that can be referenced elsewhere.

```toml
[models.fast]
provider = "openai"
model = "gpt-4o-mini"
temperature = 0.2

[models.strong]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
temperature = 0.4
```

### [memory]

Configure the memory backend.

```toml
[memory]
backend = "sqlite"
path = ".hivemind/memory.db"
```

### [tools]

Control which tools are loaded and how they are selected.

```toml
[tools]
enabled = ["web_search", "file_reader", "code_exec"]
top_k = 5
```

### [cache]

Task result caching settings.

```toml
[cache]
enabled = true
backend = "sqlite"
ttl = 86400
```

### [knowledge]

Knowledge graph configuration.

```toml
[knowledge]
backend = "sqlite"
path = ".hivemind/knowledge.db"
```

### [telemetry]

Controls telemetry and logging.

```toml
[telemetry]
enabled = false
endpoint = "https://telemetry.example.com"
```

### [bus]

Event bus configuration for inter-agent communication.

```toml
[bus]
backend = "local"
```

### [nodes]

Distributed mode settings. See [hivemind node](/docs/cli/overview) for CLI commands.

```toml
[nodes]
role = "coordinator"
bind = "0.0.0.0:9400"
workers = 4
```

### [providers.azure]

Azure OpenAI provider configuration.

```toml
[providers.azure]
endpoint = "https://my-resource.openai.azure.com"
api_version = "2024-02-01"
deployment = "gpt-4o"
```

## Environment Variable Overrides

Any config value can be overridden with an environment variable using the `HIVEMIND_` prefix and underscore-separated section paths:

```bash
export HIVEMIND_WORKER_MODEL="gpt-4o-mini"
export HIVEMIND_PLANNER_MODEL="claude-sonnet-4-20250514"
export HIVEMIND_MAX_WORKERS=8
export HIVEMIND_CACHE_ENABLED=true
```

Environment variables always take the highest priority.

## Credentials Management

API keys are stored securely in the OS keychain, not in config files. Use the `hivemind credentials` command to manage them:

```bash
hivemind credentials set openai        # prompt for API key
hivemind credentials list              # list stored credentials
hivemind credentials delete openai     # remove a credential
hivemind credentials export --env      # export as env vars
```

See the [CLI overview](/docs/cli/overview) for all credential subcommands.

## Example hivemind.toml

```toml
[swarm]
worker_model = "gpt-4o"
planner_model = "gpt-4o"
max_workers = 4
events_dir = ".hivemind/events"

[memory]
backend = "sqlite"
path = ".hivemind/memory.db"

[tools]
enabled = ["web_search", "file_reader"]
top_k = 5

[cache]
enabled = true
ttl = 86400
```

## Using Config in Python Code

You can load the resolved configuration programmatically:

```python
from hivemind.config import load_config

config = load_config()
print(config.swarm.worker_model)
print(config.tools.enabled)
```

The `load_config()` function applies the full priority chain (env > project > user > defaults) and returns a typed config object.

Verify your configuration at any time with:

```bash
hivemind doctor
```

This checks config validity, credential availability, model access, and tool loading.
