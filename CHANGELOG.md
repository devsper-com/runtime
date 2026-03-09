# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.7.0] - 2026-03-09

### Added

- **Critic role (v1.7)** — Lightweight second-pass reviewer that scores task results (completeness, accuracy, actionability) and can request one retry when score &lt; threshold. Runs on the fast model. New module `hivemind/agents/critic.py` (`CriticAgent`, `CritiqueResult`). Config: `[swarm] critic_enabled`, `critic_threshold`, `critic_roles`. Task model: `retry_count`. RunReport: `tasks_critiqued`, `tasks_retried_by_critic`, `avg_critique_score`. Event: `TASK_CRITIQUED`.
- **Agent-to-agent messaging (v1.7)** — Per-run pub/sub message bus so agents can share discoveries. New module `hivemind/agents/message_bus.py` (`SwarmMessageBus`, `AgentMessage`). Agents receive "Shared Discoveries" context and can prefix responses with `BROADCAST: <finding>` to publish. Config: `[swarm] message_bus_enabled`. Event: `AGENT_BROADCAST`.
- **Speculative pre-fetching (v1.7)** — While a task runs, pre-warm memory context and tool selection for likely successor tasks. New module `hivemind/swarm/prefetcher.py` (`TaskPrefetcher`, `PrefetchResult`). Executor triggers prefetch for speculative tasks; agent accepts optional `prefetch_result` and skips memory/tool fetch when present. RunReport: `prefetch_hit_rate`. Config: `[swarm] prefetch_enabled`, `prefetch_max_age_seconds`. Events: `PREFETCH_HIT`, `PREFETCH_MISS`.
- **Structured output self-correction (v1.7)** — Workflow steps with `output_schema` retry with a correction prompt when JSON parsing fails (strip markdown fences, validate required fields and types). New in `hivemind/workflow/runner.py`: `try_parse_structured`, `ParseResult`, `_format_schema`, `_run_step_with_correction`, `WorkflowStepError`. Event: `TASK_STRUCTURED_OUTPUT_CORRECTED`.
- **Config:** `[swarm]` v1.7 keys: `critic_enabled`, `critic_threshold`, `critic_roles`, `message_bus_enabled`, `prefetch_enabled`, `prefetch_max_age_seconds`.
- **Tests:** `tests/test_v17.py` (critic retry/no-retry/max-one, message bus broadcast/exclude-own, prefetch consumed/stale, structured correction strip/error/max-attempts).

### Changed

- Executor accepts optional `critic_agent`, `critic_enabled`, `critic_roles`, `fast_model`, `prefetcher`; runs critic loop after task success for eligible roles and may re-queue one retry.
- Agent accepts optional `message_bus` and `prefetch_result`; injects shared discoveries and uses pre-warmed context when provided.
- Swarm creates one `SwarmMessageBus` per run (when `message_bus_enabled`) and optional `TaskPrefetcher` when speculative execution and `prefetch_enabled`; passes them to executor and agent.
- Workflow steps with `output_schema` use the self-correction loop instead of blind retry; `WorkflowStepError` raised when retries exhausted.

## [1.6.0] - 2026-03-09

### Added

- **Fast Path Execution Engine (v1.6)** — Four independent optimizations for the common case:
  - **Semantic task cache** — Embedding-based similarity lookup instead of exact match only. Configure `[cache]` with `semantic = true`, `similarity_threshold`, `max_age_hours`. New events: `TASK_CACHE_HIT` (task_id, similarity, original_description), `TASK_CACHE_MISS`. Bypass: `HIVEMIND_DISABLE_SEMANTIC_CACHE=1`.
  - **Model complexity routing** — Route tasks to fast / worker / quality models by tier (simple, medium, complex). New `[models]` keys: `fast`, `quality`. New event: `TASK_MODEL_SELECTED` (task_id, tier, model). RunReport: `model_tier_breakdown`, `estimated_cost_without_routing`, `theoretical_sequential_duration`, `actual_duration`, `parallelism_efficiency`.
  - **Streaming DAG unblocking** — Dependents start as soon as each task completes (continuous unblocking) instead of wave-based execution.
  - **Parallel tool execution** — Independent tool calls in a single agent turn run in parallel. Config: `swarm.parallel_tools` (default true). Bypass: `HIVEMIND_DISABLE_PARALLEL_TOOLS=1`.
- **CLI: `hivemind cache tune [--threshold 0.90]`** — Re-evaluate last 50 semantic cache entries at different thresholds for calibration.
- **CLI: `hivemind cache stats`** — Now shows semantic cache status (threshold, entries, hit rate / avg similarity / tokens saved when available).
- **Config:** `[cache]` section (`enabled`, `semantic`, `similarity_threshold`, `max_age_hours`), `[swarm]` `parallel_tools`, `[models]` `fast` and `quality`.
- **Tests:** `tests/test_v16.py` (semantic cache, complexity router, streaming DAG, parallel tools). **Benchmarks:** `tests/benchmarks/test_v16_perf.py` (cache lookup, complexity classification, parallel tools, streaming vs wave).

### Changed

- Executor uses streaming DAG by default; wave-based execution when `streaming_dag=False`.
- Agent accepts `model_override` and `parallel_tools`; tool loop can run multiple tool calls in parallel when `parallel_tools` is true.

## [1.5.0] - 2026-03-09

### Added

- **Run analysis (v1.5)** — Post-run analysis, run history, and interactive TUI controls.
- **New module `hivemind/intelligence/analysis/`** — `run_report.py` (RunReport, TaskSummary, `build_report_from_events`), `cost_estimator.py` (CostEstimator, MODEL_PRICING), `analyzer.py` (LLM plain-English analysis), `formatter.py` (Rich CLI output).
- **CLI: `hivemind analyze <run_id>`** — Build run report from event log; optional `--no-ai` (stats only) and `--json` (raw RunReport). With a path (e.g. `.`) runs repository analysis instead.
- **CLI: `hivemind run-analyze <run_id> [--no-ai] [--json]`** — Explicit run analysis command.
- **CLI: `hivemind runs`** — List run history (Rich table: Run ID, Task, Strategy, Status, Duration, Tasks, Cost, Date). Options: `--limit N`, `--failed`, `--json`. `hivemind runs <run_id>` is shorthand for `hivemind run-analyze <run_id> --no-ai`.
- **Run history** — `hivemind/runtime/run_history.py`: SQLite DB at `~/.config/hivemind/runs.db`; `record_run`, `list_runs`, `get_run`, `delete_run`, `get_stats`. Automatically called at SWARM_FINISHED.
- **TUI: Pause/Resume (keybind `p`)** — SwarmController `pause()`/`resume()` on Swarm; executor checks `pause_event` before picking new tasks; status bar shows "⏸ PAUSED" when paused.
- **TUI: Inject (keybind `i`)** — Overlay "Inject note to swarm"; stored as high-priority MemoryRecord (episodic, tag `user_injection`); MemoryRouter.get_memory_context includes injections; activity feed shows "📌 User injected: {message}".
- **TUI: Task detail (Enter on selected task)** — In Dashboard Tasks view, arrow-key selection and Enter opens detail overlay: full description, result, tools, duration, retry, error.
- **`hivemind doctor`** — Run history checks: DB exists, "Run history: {N} runs, ${cost} total spend"; warns if any run in last 7 days has >50% task failure rate.
- **Tests** — `tests/test_analysis.py`: build_report_from_events, critical path, bottleneck, cost estimate (known/unknown model), run history record/list, runs CLI output, pause stops new tasks, inject in memory context.

### Changed

- Swarm records each run to RunHistory at SWARM_FINISHED.
- Executor accepts optional `pause_event` (threading.Event); when clear, no new tasks start until set.
- MemoryRouter.get_memory_context prepends records with tag `user_injection`.
- MemoryStore.list_memory accepts optional `tag_contains` filter.
- Event type `USER_INJECTION` for inject events in the activity feed.

## [1.4.0] - 2026-03-09

### Added

- **Workflow pipeline engine (v1.4)** — Replaced the sequential step runner with a full pipeline: **typed outputs** between steps, **conditional branching** (`if:`), **explicit dependencies** (`depends_on`), and a **validator** command.
- **New module `hivemind/workflow/`** — `schema.py` (Pydantic DSL: WorkflowDefinition, WorkflowStep, OutputField, StepCondition), `context.py` (WorkflowContext, StepResult, template resolution `{input.x}`, `{steps.id.result}`, `{steps.id.field}`), `conditions.py` (safe `if:` expression evaluation, no eval), `resolver.py` (topological sort, waves, cycle detection), `validator.py` (ValidationReport, reference/DAG/condition checks, dead-output warnings), `runner.py` (WorkflowRunner with parallel waves, retries, output_schema parsing). Loader returns `WorkflowDefinition`; legacy list-of-strings workflows still load and run.
- **CLI:** `hivemind workflow list` — List workflows (name, version, step count, description). `hivemind workflow validate <name>` — Validate and print report (✓/✗/⚠ with Rich). `hivemind workflow run <name> [--input KEY=VALUE ...]` — Run with runtime inputs and summary table. `hivemind workflow <name>` still runs the workflow (backward compatible).
- **Workflow TOML format** — Steps can define `id`, `task`, `depends_on`, `if` (expression), `output_schema` (list of name/type/required), `role`, `model`, `retry`, `timeout_seconds`. Inputs declared in `inputs`; templates use `{input.x}` and `{steps.step_id.result}` or `{steps.step_id.field}` from structured output.
- **Tests** — `tests/test_workflow.py`: sequential/parallel execution, condition skips/blocking, template resolution, output_schema parsing, cycle detection, validator bad reference and dead-output warning, backward compat.

### Changed

- `load_workflow(name)` now returns `WorkflowDefinition | None` (Pydantic model). Legacy workflows (steps as list of strings) are wrapped with auto-generated step ids and sequential dependencies.
- `run_workflow(steps, ...)` (legacy) now uses WorkflowRunner under the hood; return type `dict[str, str]` (step_id → result) unchanged.

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
