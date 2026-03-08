<p align="center">
  <img src="branding/logo.svg" alt="Hivemind" width="120" height="120" />
</p>

# Hivemind

**Distributed AI Swarm Runtime**

[![PyPI version](https://badge.fury.io/py/hivemind-ai.svg)](https://pypi.org/project/hivemind-ai/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/downloads/)

Hivemind is a **distributed AI swarm runtime** for coordinating large numbers of AI agents across complex tasks. Orchestrate multi-agent systems with a **swarm execution model**: tasks are decomposed into subtasks, executed in parallel, and coordinated through a scheduler and dependency graph.

> **Install:** PyPI package is **`hivemind-ai`**; CLI command is **`hivemind`**.

---

## Features

- **Planner** → **Scheduler** → **Executor** → **Agents** — DAG-based task execution with configurable parallelism
- **Strategy-based planning** — Auto-selected strategies (research, code analysis, data science, document, experiment) output DAGs; fallback to LLM planning
- **120+ tools** — Research, coding, data science, documents, experiments, memory, filesystem; **smart tool selection** (top-k by similarity to task)
- **TOML configuration** — `hivemind.toml` / `workflow.hivemind.toml` with Pydantic validation; env > project > user > defaults
- **Memory & knowledge graph** — Episodic, semantic, research, artifact memory; summarization, namespaces, scoring; entity search and relationship traversal
- **Map-reduce runtime** — `swarm.map_reduce(dataset, map_fn, reduce_fn)` using the worker pool
- **Workflows** — Define steps in `workflow.hivemind.toml`; run with `hivemind workflow <name>`
- **Plugin ecosystem** — Discover tools via entry_points (`hivemind.plugins`)
- **Provider routing** — OpenAI, Anthropic, Azure, Gemini, **GitHub Models (Copilot)** (model name or `provider:model` spec)
- **Automatic model routing** — Set `planner = "auto"` and `worker = "auto"` in config for cost/latency/quality-aware selection
- **EventLog, replay, telemetry** — Structured events for debugging and metrics
- **CLI & TUI** — `hivemind init`, `hivemind doctor`, `hivemind run`, `hivemind research`, `hivemind analyze`, `hivemind memory`, `hivemind query`, `hivemind workflow`, `hivemind tui` with dashboard (tasks, swarm graph, memory, activity feed, knowledge graph, logs)

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

## Quickstart

**Install (Python 3.12+):**

```bash
pip install hivemind-ai
# or: uv add hivemind-ai
```

**Quick setup (new project):**

```bash
export GITHUB_TOKEN=...   # or OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
hivemind init
hivemind run "analyze this repository"
```

**Run a task:**

```bash
hivemind run "Summarize swarm intelligence in one paragraph."
```

**Use in code (with config file):**

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```

**Or with explicit parameters:**

```python
from hivemind import Swarm

swarm = Swarm(worker_count=4, worker_model="gpt-4o-mini", planner_model="gpt-4o-mini", use_tools=True)
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```

Set API keys via environment or config (see [Configuration](#configuration) below).

---

## CLI usage

| Command | Description |
|--------|-------------|
| `hivemind init` | Set up a new project (creates `hivemind.toml`, example workflow, dataset folder) |
| `hivemind doctor` | Verify environment (GITHUB_TOKEN, OpenAI keys, config file, tool registry) |
| `hivemind run "task"` | Run swarm with the given task |
| `hivemind tui` | Launch terminal UI (prompt + output + dashboard) |
| `hivemind research papers/` | Literature review on a directory of papers |
| `hivemind analyze repo/` | Analyze repository architecture |
| `hivemind memory [--limit N]` | List memory entries |
| `hivemind query "diffusion models"` | Query knowledge graph (entity search, relationships) |
| `hivemind workflow <name>` | Run a workflow by name (from `workflow.hivemind.toml`) |

---

## TUI usage

```bash
hivemind tui
```

- **Prompt** — Type a task and press **Enter** or **r** to run.
- **Output** — Response and step status (e.g. “Planning…”, “Step 2 of 5…”).
- **Dashboard (d)** — Tasks, swarm graph, memory, activity feed, knowledge graph viewer, logs.
- **Keys:** `r` Run, `d` Dashboard, `Esc` Unfocus, `o` Output, `q` Quit.

---

## Examples

| Workflow | Command |
|----------|---------|
| Literature review | `hivemind research papers/` or `uv run python examples/research/literature_review.py [dir]` |
| Repository analysis | `hivemind analyze .` or `uv run python examples/coding/analyze_repository.py [path]` |
| Dataset analysis | `uv run python examples/data_science/dataset_analysis.py [path-to.csv]` |
| Document intelligence | `uv run python examples/documents/analyze_documents.py [dir]` |
| Parameter sweep | `uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01,0.1]}'` |

Outputs go to `examples/output/`. Run from project root when using script paths.

---

## Demo GIF

To create a demo GIF showing swarm execution and task progress:

1. Start the TUI: `hivemind tui`
2. Use a screen recorder (e.g. [asciinema](https://asciinema.org/), [LICEcap](https://www.cockos.com/licecap/), or terminal GIF tools) to record:
   - Typing a task in the prompt (e.g. “Summarize swarm intelligence in one paragraph”)
   - Pressing Enter to run
   - The spinner and step status (Planning…, Executing step 1 of N…)
   - The final response appearing
   - Optionally pressing **d** to open the Dashboard (tasks, swarm graph, memory, logs)
3. Export the recording as a GIF and add it to the README or docs (e.g. `![Demo](docs/demo.gif)`).

Example asciinema:

```bash
asciinema rec demo.cast
# run: hivemind tui, then run a task and optionally open dashboard
# exit TUI (q), then Ctrl-D to stop rec
# convert: asciinema-agg demo.cast demo.gif  # or use asciinema’s playback + another tool for GIF
```

---

## Configuration

Config order: **env** > **project** config > **user** `~/.config/hivemind/config.toml` > defaults.

**Config locations:** `./hivemind.toml`, `./workflow.hivemind.toml`, `~/.config/hivemind/config.toml`, or legacy `.hivemind/config.toml`.

**GitHub Models (Copilot):** Use `provider:model` and set `GITHUB_TOKEN`. Example: `github:gpt-4o`, `github:claude-3.5-sonnet`, `github:phi-3`.

**Automatic model routing:** Set `planner = "auto"` and `worker = "auto"` in `[models]`; the router picks a model by task type (planning → high quality, fast → low cost).

**Example `hivemind.toml` (v1 format):**

```toml
[swarm]
workers = 6
adaptive_planning = true
max_iterations = 10

[models]
planner = "auto"
worker = "auto"
# Or explicit: planner = "azure:gpt-4o", worker = "github:gpt-4o"

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
endpoint = ""
deployment = ""
```

**Legacy format** (still supported): use `[default]` with `worker_model`, `planner_model`, `events_dir`, `data_dir`.

**Env overrides:** `HIVEMIND_WORKER_MODEL`, `HIVEMIND_PLANNER_MODEL`, `HIVEMIND_EVENTS_DIR`, `HIVEMIND_DATA_DIR`, plus provider keys (`OPENAI_API_KEY`, `AZURE_OPENAI_*`, etc.). See [docs/providers.md](docs/providers.md), [docs/configuration.md](docs/configuration.md), and [docs/development.md](docs/development.md).

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Introduction](docs/introduction.md) | What Hivemind is, problem it solves, core concepts |
| [Architecture](docs/architecture.md) | Planner, Scheduler, Executor, Agents, Tools, Memory, strategies, config, map-reduce |
| [Configuration](docs/configuration.md) | TOML config (v1), schema, locations, env overrides |
| [Swarm runtime](docs/swarm_runtime.md) | Task lifecycle, flow, code snippets, map-reduce |
| [Tools](docs/tools.md) | Tool architecture, registry, runner, smart tool selection, plugins |
| [Memory](docs/memory_system.md) | Memory types, store, retrieval, summarization, namespaces, scoring |
| [Providers](docs/providers.md) | Provider routing, model spec, Azure |
| [CLI](docs/cli.md) | All CLI commands (run, tui, research, analyze, memory, query, workflow) |
| [TUI](docs/tui.md) | Layout, panels (activity feed, knowledge graph), keyboard shortcuts |
| [Examples](docs/examples.md) | Example workflows and commands |
| [Development](docs/development.md) | Project structure, adding tools/plugins/workflows, setup |
| [Contributing](CONTRIBUTING.md) | Setup, testing, code style, PR guidelines |
| [FAQ](docs/faq.md) | Common questions |

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, testing, and PR guidelines.

---

## License

Hivemind is licensed under **GPL-3.0-or-later**. See [LICENSE](LICENSE) for the full text.
