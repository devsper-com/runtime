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

> **Install:** PyPI package **`hivemind-ai`** · CLI command **`hivemind`**

---

## Features

- **Planner → Scheduler → Executor → Agents** — DAG-based execution with configurable parallelism
- **Strategy-based planning** — Auto-selected strategies (research, code, data science, document, experiment) or LLM fallback
- **120+ tools** — Research, coding, data science, documents, experiments, memory; **smart tool selection** (top-k by similarity)
- **TOML config** — `hivemind.toml` / `workflow.hivemind.toml` with Pydantic validation; env > project > user > defaults
- **Memory & knowledge graph** — Episodic, semantic, research, artifact memory; summarization, namespaces, entity/relationship search
- **Map-reduce runtime** — `swarm.map_reduce(dataset, map_fn, reduce_fn)` using the worker pool
- **Workflows** — Define steps in `workflow.hivemind.toml`; run with `hivemind workflow <name>`
- **Plugin ecosystem** — Discover tools via entry_points (`hivemind.plugins`)
- **Provider routing** — OpenAI, Anthropic, Azure, Gemini, **GitHub Models (Copilot)** (`provider:model` or model name)
- **Automatic model routing** — `planner = "auto"` and `worker = "auto"` for cost/latency/quality-aware selection
- **EventLog, replay, telemetry** — Structured events for debugging and metrics
- **CLI & TUI** — `hivemind init`, `hivemind doctor`, `hivemind run`, `hivemind research`, `hivemind analyze`, `hivemind memory`, `hivemind query`, `hivemind workflow`, `hivemind tui` (dashboard: tasks, swarm graph, memory, activity feed, knowledge graph, logs)

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

**New project:**

```bash
export GITHUB_TOKEN=...   # or OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
hivemind init
hivemind run "analyze this repository"
```

**Run a task:**

```bash
hivemind run "Summarize swarm intelligence in one paragraph."
```

**In code (config file):**

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```

**Or explicit parameters:**

```python
from hivemind import Swarm

swarm = Swarm(worker_count=4, worker_model="gpt-4o-mini", planner_model="gpt-4o-mini", use_tools=True)
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```

Set API keys via environment or config (see [Configuration](#configuration)).

---

## CLI

| Command | Description |
|--------|-------------|
| `hivemind init` | Set up a new project (`hivemind.toml`, example workflow, dataset folder) |
| `hivemind doctor` | Verify environment (GITHUB_TOKEN, OpenAI keys, config, tool registry) |
| `hivemind run "task"` | Run swarm with the given task |
| `hivemind tui` | Terminal UI (prompt, output, dashboard) |
| `hivemind research papers/` | Literature review on a directory of papers |
| `hivemind analyze repo/` | Analyze repository architecture |
| `hivemind memory [--limit N]` | List memory entries |
| `hivemind query "…"` | Query knowledge graph (entity search, relationships) |
| `hivemind workflow <name>` | Run a workflow from `workflow.hivemind.toml` |

**TUI:** Prompt + **Enter** or **r** to run; **d** for dashboard (tasks, swarm graph, memory, activity feed, knowledge graph, logs). **Esc** unfocus, **o** output, **q** quit.

---

## Examples

| Workflow | Command |
|----------|---------|
| Literature review | `hivemind research papers/` or `uv run python examples/research/literature_review.py [dir]` |
| Repository analysis | `hivemind analyze .` or `uv run python examples/coding/analyze_repository.py [path]` |
| Dataset analysis | `uv run python examples/data_science/dataset_analysis.py [path-to.csv]` |
| Document intelligence | `uv run python examples/documents/analyze_documents.py [dir]` |
| Parameter sweep | `uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01,0.1]}'` |

Outputs under `examples/output/`. Run from project root when using script paths.

---

## Configuration

**Priority:** env > project config > user `~/.config/hivemind/config.toml` > defaults.

**Locations:** `./hivemind.toml`, `./workflow.hivemind.toml`, `~/.config/hivemind/config.toml`, or legacy `.hivemind/config.toml`.

**GitHub Models (Copilot):** Use `provider:model` and set `GITHUB_TOKEN`. Example: `github:gpt-4o`, `github:claude-3.5-sonnet`, `github:phi-3`.

**Automatic model routing:** Set `planner = "auto"` and `worker = "auto"` in `[models]`; the router picks by task type (planning → quality, fast → cost).

**Example `hivemind.toml`:**

```toml
[swarm]
workers = 6
adaptive_planning = true
max_iterations = 10

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
endpoint = ""
deployment = ""
```

Legacy `[default]` with `worker_model`, `planner_model`, `events_dir`, `data_dir` is still supported. Env overrides: `HIVEMIND_WORKER_MODEL`, `HIVEMIND_PLANNER_MODEL`, `HIVEMIND_EVENTS_DIR`, `HIVEMIND_DATA_DIR`, plus provider keys. See [docs/providers.md](docs/providers.md), [docs/configuration.md](docs/configuration.md), [docs/development.md](docs/development.md).

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Introduction](docs/introduction.md) | What Hivemind is, problem, core concepts |
| [Architecture](docs/architecture.md) | Planner, Scheduler, Executor, Agents, Tools, Memory, strategies, config, map-reduce |
| [Configuration](docs/configuration.md) | TOML schema, locations, env overrides |
| [Swarm runtime](docs/swarm_runtime.md) | Task lifecycle, flow, map-reduce |
| [Tools](docs/tools.md) | Registry, runner, smart selection, plugins |
| [Memory](docs/memory_system.md) | Types, store, retrieval, summarization, namespaces, knowledge graph |
| [Providers](docs/providers.md) | Provider routing, model spec, Azure, GitHub Models, auto routing |
| [CLI](docs/cli.md) | Commands: run, tui, research, analyze, memory, query, workflow, init, doctor |
| [TUI](docs/tui.md) | Layout, panels, shortcuts |
| [Examples](docs/examples.md) | Workflows and commands |
| [Development](docs/development.md) | Structure, adding tools/plugins/workflows |
| [Contributing](CONTRIBUTING.md) | Setup, testing, PR guidelines |
| [FAQ](docs/faq.md) | Common questions |

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

**GPL-3.0-or-later** — see [LICENSE](LICENSE).
