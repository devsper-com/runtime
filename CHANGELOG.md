# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-03-09

### Added

- **Tool Reliability Scoring (v1.3)** — Every tool gets a runtime score from real usage; scores feed into tool selection so unreliable tools are demoted over time.
- **`hivemind tools`** — List registered tools with reliability scores (table: Tool Name, Category, Score, Label, Success Rate, Avg Latency, Calls, Last Used). Options: `--category <name>`, `--poor` (score &lt; 0.40). Subcommand `reset <tool_name>` or `reset --all` (with confirmation) wipes score history. Rows colored by label (excellent=green, good=default, degraded=yellow, poor=red); tools with &lt;5 calls show "new".
- **Scoring module** (`hivemind/tools/scoring/`): `ToolScoreStore` (SQLite at `~/.config/hivemind/tool_scores.db`), `ToolScore` dataclass, `record_tool_result`, `get_tool_score`, `get_default_score_store`; `compute_composite_score` and `score_label` in `scorer.py`; `select_tools_scored` (70% similarity + 30% reliability) in `selector.py`; `generate_tools_report` in `report.py`. New tools (&lt;5 calls) get neutral 0.75; `HIVEMIND_DISABLE_TOOL_SCORING=1` bypasses scoring for tests.
- **`hivemind doctor`** — Tool scoring checks: info line "Tool scoring database: {N} records, {M} tools tracked"; warns if &gt;20% of tools with 10+ calls are poor; suggests `hivemind tools reset <name>` for tools with 0% success and ≥10 calls.
- **`hivemind analytics`** — Appends tool reliability report (summary, top 3, bottom 3) when scores exist.
- **Agent** — Uses blended tool selection (similarity × reliability) and passes `task_type` (role or "general") into tool runner for per-context scoring.
- **Tests** — `tests/test_tool_scoring.py`: composite score (new/reliable/dead), score_label, store record/retrieve/prune/reset, selector prefers reliable, similarity dominates, env bypass.

### Changed

- `run_tool(name, args, task_type=None)` now records each run to the scoring store (success/failure, latency, error_type).
- `get_tools_for_task(..., score_store=None)` uses `select_tools_scored` when a score store is provided and scoring is not disabled.

## [1.2.0] - 2026-03-09

### Added

- **`hivemind build`** — Autonomous application builder: generate a working repository from an app description. Orchestrates scaffold → implement → test → debug loop with isolated sandbox and code intelligence (repo index, dependency graph). Use `hivemind build "fastapi todo app"` or `-o ./output` for custom output directory.
- **`hivemind credentials`** — Manage API keys and secrets via the OS keychain (keyring): `set`, `list`, `delete`, `migrate` from `.env`/config, `export` for sourcing. Documented in [CLI](docs/cli.md). Config resolver injects keyring credentials when env vars are not set.
- **`hivemind upgrade`** — Check for updates (PyPI), show changelog between versions, detect installer (pip/uv), and perform upgrade. Supports `--check`, `-y`, `--version`, `--dry-run`. Optional in-session update notice when a new version is available.
- **Credentials module** (`hivemind/credentials/`): `CredentialStore`, keyring-backed storage, migration from config/`.env`.
- **Upgrade module** (`hivemind/upgrade/`): version check with 24h cache, changelog fetch/parse, installer detection, notifier.
- **Dev module** (`hivemind/dev/`): builder, scaffold, sandbox, debugger, repo_index for autonomous app building.
- New dependency: `keyring>=24.0` for secure credential storage.

### Changed

- Config resolution injects credentials from the keyring when the corresponding environment variables are not set, so providers work without storing secrets in config files.
- TUI: dashboard and dev view updates.
- Docs: CLI reference includes `credentials`; configuration and FAQ updated.

## [1.1.1] - 2026-03-09

### Changed

- README logo now uses GitHub raw URL so it displays on PyPI.

## [1.1.0] - 2026-03-09

### Added

- **`hivemind init`** — Set up a new project (creates `hivemind.toml`, example workflow, dataset folder). Documented in [CLI](docs/cli.md).
- **`hivemind doctor`** — Verify environment (API keys, config file, tool registry). Documented in [CLI](docs/cli.md).
- **GitHub Models (Copilot)** — Provider routing with `github:model` (e.g. `github:gpt-4o`, `github:claude-3.5-sonnet`). Set `GITHUB_TOKEN`. Documented in [Providers](docs/providers.md).
- **Automatic model routing** — `planner = "auto"` and `worker = "auto"` in `[models]` for cost/latency/quality-aware selection. Documented in [Providers](docs/providers.md) and [Configuration](docs/configuration.md).

### Changed

- README: PyPI badge fixed (shields.io), badges centered, styling and bloat removed.
- Docs: CLI reference now includes `init` and `doctor`; providers doc covers GitHub Models and auto routing; configuration doc describes `"auto"` for `[models]`.

## [1.0.0] - 2025-03-08

### Added

- **TOML configuration system** (`hivemind/config/`): Pydantic-validated config with `config_loader`, `schema`, `defaults`, `resolver`. Locations: `./hivemind.toml`, `./workflow.hivemind.toml`, `~/.config/hivemind/config.toml`. Priority: env > project > user > defaults. Sections: `[swarm]`, `[models]`, `[memory]`, `[tools]`, `[telemetry]`, `[providers.azure]`.
- **Strategy-based planning** (`hivemind/intelligence/strategies/`): Research, code analysis, data science, document pipeline, and experiment strategies that output DAG tasks. Planner selects strategy automatically (keyword heuristics) and uses strategy DAG when applicable; otherwise falls back to LLM planning.
- **Smart tool selection** (`hivemind/tools/selector.py`): Embed task and tools, select top_k by similarity. Config `[tools] top_k` and `enabled` categories. Optional `category` on Tool base.
- **Map-reduce swarm runtime** (`hivemind/swarm/map_reduce.py`): `swarm.map_reduce(dataset, map_fn, reduce_fn)` with parallel map and single reduce using worker pool.
- **Memory evolution**: `summarizer.py` (extractive/LLM summarization), `namespaces.py` (research_memory, coding_memory, dataset_memory via tags), `scoring.py` (recency, importance, combined ranking).
- **Knowledge graph queries** (`hivemind/knowledge/query.py`): Entity search and relationship traversal. CLI: `hivemind query "diffusion models"`.
- **Plugin ecosystem** (`hivemind/plugins/`): Discover tools via entry_points (`hivemind.plugins`). `plugin_loader.py`, `plugin_registry.py`. Tools package loads plugins after built-in categories.
- **Workflow files**: Load workflows from `workflow.hivemind.toml` (`[workflow] name`, `steps`). CLI: `hivemind workflow <name>`.
- **TUI v2**: Activity Feed and Knowledge Graph viewer panels in dashboard; Memory view supports optional namespace filter.
- **SDK improvements**: `Swarm(config="hivemind.toml")` and `from hivemind import Swarm, get_config`. Config populates worker_count, models, adaptive, use_tools; kwargs override config.
- **Benchmark suite** (`benchmarks/`): bench_research_pipeline, bench_repository_analysis, bench_dataset_analysis (mocked LLM).
- Tests for config loader, strategies, tool selector, map_reduce, memory evolution, plugins, workflow, knowledge query.

### Changed

- Config is now a package `hivemind/config/`; legacy paths (`.hivemind/config.toml`, `[default]`) still supported and mapped into new schema.
- Strategy selector extended with DOCUMENT and EXPERIMENT strategies; planner accepts optional strategy and prompt_suffix.
- Swarm constructor accepts optional `config` (path or object); existing keyword arguments override config.

### Backward compatibility

- v0.1 APIs preserved: `get_config()` returns an object with `worker_model`, `planner_model`, `events_dir`, `data_dir`. `Swarm(worker_count=4, ...)` without config works as before. All existing tests pass.

## [0.1.0] - (existing release)

- Initial release: Planner, Scheduler, Executor, Swarm, Agents, 120+ tools, memory system, knowledge graph, provider routing (OpenAI, Anthropic, Gemini, Azure), EventLog, replay, telemetry, CLI, TUI, examples.
