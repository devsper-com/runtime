# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
