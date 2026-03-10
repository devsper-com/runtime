<p align="center">
  <img src="https://raw.githubusercontent.com/rithulkamesh/hivemind/refs/heads/main/branding/logo.svg" alt="Hivemind" width="120" height="120" />
</p>

<h1 align="center">Hivemind</h1>
<p align="center"><strong>Distributed AI Swarm Runtime</strong></p>

<p align="center">
  <a href="https://pypi.org/project/hivemind-ai/"><img src="https://img.shields.io/pypi/v/hivemind-ai?label=PyPI" alt="PyPI"></a>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-green.svg" alt="Python 3.12+"></a>
</p>

<p align="center">
  <em>Orchestrate multi-agent systems with a swarm execution model: tasks → DAG → parallel execution.</em>
</p>

> **Install:** PyPI package **`hivemind-ai`** · CLI **`hivemind`**

---

## Quick start

**1. Install (Python 3.12+):**

```bash
pip install hivemind-ai
# or: uv add hivemind-ai
```

**2. Set up API keys (pick one):**

Store credentials in your OS keychain so you never re-enter them:

```bash
hivemind credentials set openai api_key      # prompts for value
hivemind credentials set anthropic api_key
hivemind credentials set github token
# or migrate from .env:
hivemind credentials migrate
```

Or use environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, etc. (see [Credentials](#credentials)).

**3. Create a project and run:**

```bash
hivemind init
hivemind run "Summarize swarm intelligence in one paragraph."
```

**4. Optional — shell completion:**

```bash
# Bash: add to ~/.bashrc
eval "$(hivemind completion bash)"

# Zsh: add to ~/.zshrc
eval "$(hivemind completion zsh)"
```

---

## Run from code

**From config file:**

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```

**Explicit parameters:**

```python
from hivemind import Swarm

swarm = Swarm(worker_count=4, worker_model="gpt-4o-mini", planner_model="gpt-4o-mini", use_tools=True)
results = swarm.run("Your task here.")
```

Credentials are injected from the keyring (or env) when config is resolved—no code changes needed.

---

## Credentials

API keys are **not** stored in config files. Use the **credential store** (OS keychain) or environment variables.

| What you want | Command or method |
|---------------|-------------------|
| Store a key securely | `hivemind credentials set <provider> <key>` (prompts; uses keyring) |
| List stored keys (no values) | `hivemind credentials list` |
| Import from `.env` / TOML | `hivemind credentials migrate` |
| Export for sourcing / `.env` | `hivemind credentials export <provider>` → prints `KEY=value` lines |
| Remove a key | `hivemind credentials delete <provider> <key>` |

**Providers:** `openai`, `anthropic`, `github`, `gemini`, `azure`, `azure_anthropic` (keys: `api_key`, `token`, `endpoint`, `deployment`, `api_version` as applicable).

**Example — export and source in a script:**

```bash
eval "$(hivemind credentials export azure)"
hivemind run "Your task"
```

See [Configuration](docs/configuration.md#credentials-api-keys) and [CLI](docs/cli.md#credentials) for details.

---

## CLI

| Command | Description |
|--------|-------------|
| `hivemind init` | Set up a new project (`hivemind.toml`) |
| `hivemind doctor` | Check environment (keys, config, tools) |
| `hivemind run "task"` | Run swarm on a task |
| `hivemind tui` | Terminal UI (prompt, dashboard, logs) |
| `hivemind credentials set/list/migrate/export/delete` | Manage API keys (keyring) |
| `hivemind completion bash \| zsh` | Print shell completion script |
| `hivemind research [path]` | Literature review on a directory |
| `hivemind analyze [path]` | Analyze repository architecture |
| `hivemind memory [--limit N]` | List memory entries |
| `hivemind query "…"` | Query knowledge graph |
| `hivemind workflow <name>` | Run a workflow from `workflow.hivemind.toml` |
| `hivemind graph [run_id]` | Export task DAG as Mermaid |
| `hivemind replay [run_id]` | Replay a run from event log |
| `hivemind cache stats \| clear` | Task result cache |
| `hivemind analytics` | Tool usage stats |
| `hivemind build "app description" [-o dir]` | Autonomous app builder |
| `hivemind upgrade [--check \| -y]` | Check for updates / upgrade |

Run `hivemind --help` or `hivemind <command> --help` for examples and options.

---

## Features

- **Planner → Scheduler → Executor → Agents** — DAG-based execution with configurable parallelism
- **Strategy-based planning** — Auto-selected strategies (research, code, data science, document, experiment) or LLM fallback
- **120+ tools** — Research, coding, data science, documents, experiments, memory; **smart tool selection** (top-k by similarity)
- **TOML config** — `hivemind.toml` / `workflow.hivemind.toml`; env > project > user > defaults
- **Memory & knowledge graph** — Episodic, semantic, research, artifact memory; summarization, namespaces, entity/relationship search
- **Map-reduce runtime** — `swarm.map_reduce(dataset, map_fn, reduce_fn)` using the worker pool
- **Workflows** — Define steps in `workflow.hivemind.toml`; run with `hivemind workflow <name>`; **structured output self-correction** (v1.7) retries with a correction prompt when JSON parsing fails
- **Critic & agent messaging (v1.7)** — Optional second-pass critic scores results and requests one retry; per-run message bus lets agents share discoveries via `BROADCAST:`
- **Speculative pre-fetching (v1.7)** — Pre-warm memory and tools for successor tasks while others run; reduces standing-up time
- **Plugin ecosystem** — Discover tools via entry_points (`hivemind.plugins`)
- **Provider routing** — OpenAI, Anthropic, Azure, Gemini, **GitHub Models (Copilot)** (`provider:model` or model name); **429 retry with backoff** for GitHub rate limits
- **Automatic model routing** — `planner = "auto"` and `worker = "auto"` for cost/latency/quality-aware selection
- **EventLog, replay, telemetry** — Structured events for debugging and metrics

---

## Architecture

```
    Planner
       ↓
    Scheduler
       ↓
    Executor
       ↓
    Agents  →  Tools  →  Memory  →  Knowledge Graph
```

---

## Configuration

**Priority:** env > project config > user `~/.config/hivemind/config.toml` > defaults.

**Locations:** `./hivemind.toml`, `./workflow.hivemind.toml`, `~/.config/hivemind/config.toml`, or legacy `.hivemind/config.toml`.

**Keep secrets out of TOML.** Use `hivemind credentials` or environment variables for API keys. Non-secret settings (models, workers, paths) go in TOML.

**Example `hivemind.toml`:**

```toml
[swarm]
workers = 6
adaptive_planning = true
max_iterations = 10
critic_enabled = true
critic_roles = ["research", "analysis", "code"]
message_bus_enabled = true
prefetch_enabled = true

[models]
planner = "auto"
worker = "auto"

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
endpoint = ""   # or use credentials store / env
deployment = ""
```

Env overrides: `HIVEMIND_WORKER_MODEL`, `HIVEMIND_PLANNER_MODEL`, `HIVEMIND_EVENTS_DIR`, `HIVEMIND_DATA_DIR`, plus provider keys. Full schema: [docs/configuration.md](docs/configuration.md), [docs/providers.md](docs/providers.md).

---

## Distributed mode (v1.10)

Run a **controller** and **workers** across processes or machines. Workers can be Python or **Rust** (`hivemind-worker` binary) for higher throughput.

```bash
# Redis + workers + controller (see examples/distributed/README.md)
docker compose up -d
uv run python examples/distributed/run_worker.py   # or Rust: HIVEMIND_WORKER_MODEL=github:gpt-4o ./worker/target/release/hivemind-worker
uv run python examples/distributed/run_controller.py "Your task" --parallel
```

Rust workers: set `HIVEMIND_WORKER_MODEL=github:gpt-4o` (or your model), `HIVEMIND_PYTHON_BIN=.venv/bin/python`, `HIVEMIND_RPC_PORT=0` for multiple workers on one host. Credentials load from keychain in the subprocess.

---

## Examples

| Workflow | Command |
|----------|---------|
| Distributed (v1.10) | `uv run python examples/distributed/run_controller.py "Task" --parallel` |
| Literature review | `hivemind research papers/` or `uv run python examples/research/literature_review.py [dir]` |
| Repository analysis | `hivemind analyze .` or `uv run python examples/coding/analyze_repository.py [path]` |
| Dataset analysis | `uv run python examples/data_science/dataset_analysis.py [path-to.csv]` |
| Document intelligence | `uv run python examples/documents/analyze_documents.py [dir]` |
| Parameter sweep | `uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01,0.1]}'` |

Outputs under `examples/output/`. Run from project root when using script paths.

---

## Documentation

Full docs (with versioning and dark mode): **[hivemind.rithul.dev](https://hivemind.rithul.dev)**. Source lives in `website/docs/` and is built with [Docusaurus](https://docusaurus.io).

| Doc | Description |
|-----|-------------|
| [Introduction](https://hivemind.rithul.dev/docs/introduction) | What Hivemind is, problem, core concepts |
| [Architecture](https://hivemind.rithul.dev/docs/architecture) | Planner, Scheduler, Executor, Agents, Tools, Memory, strategies |
| [Configuration](https://hivemind.rithul.dev/docs/configuration) | TOML schema, locations, env, **credentials** |
| [Swarm runtime](https://hivemind.rithul.dev/docs/swarm_runtime) | Task lifecycle, flow, map-reduce |
| [Tools](https://hivemind.rithul.dev/docs/tools) | Registry, runner, smart selection, plugins |
| [Memory](https://hivemind.rithul.dev/docs/memory_system) | Types, store, retrieval, knowledge graph |
| [Providers](https://hivemind.rithul.dev/docs/providers) | Provider routing, Azure, GitHub Models, auto routing |
| [CLI](https://hivemind.rithul.dev/docs/cli) | All commands, **credentials**, completion |
| [TUI](https://hivemind.rithul.dev/docs/tui) | Layout, panels, shortcuts |
| [Examples](https://hivemind.rithul.dev/docs/examples) | Workflows and commands |
| [Development](https://hivemind.rithul.dev/docs/development) | Structure, adding tools/plugins/workflows |
| [Contributing](CONTRIBUTING.md) | Setup, testing, PR guidelines |
| [FAQ](https://hivemind.rithul.dev/docs/faq) | Common questions |

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

**GPL-3.0-or-later** — see [LICENSE](LICENSE).
