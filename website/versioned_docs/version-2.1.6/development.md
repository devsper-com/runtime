# Development Guide

## Project structure

High-level layout:

```
hivemind/
  agents/          # Agent (LLM worker)
  config/          # TOML config: config_loader, schema, defaults, resolver (Pydantic)
  swarm/           # Planner, Scheduler, Executor, Swarm, map_reduce
  tools/           # Tool base, registry, runner, selector, categories (research, coding, …)
  memory/          # MemoryStore, MemoryRouter, MemoryIndex, summarizer, namespaces, scoring
  knowledge/       # Knowledge graph, query
  intelligence/    # Strategy selector, strategies/ (research, code_analysis, …), task optimizer
  plugins/         # plugin_loader, plugin_registry (entry_points)
  workflow/        # Workflow loader, runner (workflow.hivemind.toml)
  providers/       # OpenAI, Anthropic, Gemini, router
  runtime/         # Replay, telemetry, visualization
  utils/           # event_logger, models (generate)
  types/           # Task, Event, task status
  cli.py           # CLI entrypoint (run, tui, research, analyze, memory, query, workflow)
  tui/             # Terminal UI (Textual): app, dashboard, activity feed, knowledge graph view
  dashboard/       # Optional dashboard components
examples/         # Research, coding, data science, documents, experiments
benchmarks/       # Benchmarks (research pipeline, repository analysis, dataset analysis)
tests/            # Pytest tests
docs/             # Documentation
```

## Development setup

1. **Clone and install:**

   ```bash
   git clone https://github.com/rithulkamesh/hivemind.git
   cd hivemind
   uv sync
   ```

   Or with pip: `pip install -e ".[dev]"` (if dev extras exist) or `pip install -e .` and install dev deps (pytest, ruff, black) manually.

2. **Config / env:**  
   Copy `.env.example` to `.env` and set API keys (OpenAI, Anthropic, Google, or Azure). Alternatively use `hivemind.toml`, `~/.config/hivemind/config.toml`, or `.hivemind/config.toml`; see [Configuration](configuration).

3. **Run tests:**

   ```bash
   uv run python -m pytest tests/ -v
   ```

4. **Lint / format:**

   ```bash
   uv run ruff check hivemind examples
   uv run black --check hivemind examples
   ```

## Adding new tools

1. Create a new file under the appropriate category (e.g. `hivemind/tools/<category>/my_tool.py`).
2. Subclass `Tool`, set `name`, `description`, `input_schema`, implement `run(**kwargs) -> str`.
3. Call `register(MyTool())` at module level.
4. Ensure the category’s `__init__.py` (or the main `hivemind.tools` package) imports the module so the tool is registered when the app loads.
5. Add tests under `tests/tools/` if needed.

See [Tools](tools) for a full example.

## Adding a plugin (v1)

1. Create a package (e.g. `hivemind-plugin-bio`) with a callable that returns a list of `Tool` instances or that calls `register(tool)` for each tool.
2. In the plugin’s `pyproject.toml`, declare the entry point:
   ```toml
   [project.entry-points."hivemind.plugins"]
   bio = "hivemind_plugin_bio:register"
   ```
3. Install the plugin in the same environment as hivemind; when `hivemind.tools` is imported, the loader will discover and run it. See [Tools](tools#plugin-system-v1).

## Adding a workflow (v1)

1. Create or edit `workflow.hivemind.toml` in the project root (or current directory):
   ```toml
   [workflow]
   name = "my_pipeline"
   steps = ["step_one", "step_two", "step_three"]
   ```
2. Run it with `hivemind workflow my_pipeline`. Steps are executed in order (each step depends on the previous). The same executor and agent stack as `hivemind run` is used; config (worker model, tools, memory) applies.

## Extending the swarm runtime

- **Custom planner:** Implement a class that, given a root `Task`, returns a list of `Task` objects with dependencies; then pass it into a custom orchestration path or swap the default planner in `Swarm`.
- **Custom executor:** The executor only needs a scheduler (with `get_ready_tasks`, `mark_completed`, `is_finished`) and an agent (with `run(task)`). You can subclass or replace `Executor` to change concurrency, retries, or batching.
- **Events:** All components use `EventLog.append_event(Event(...))`. New event types can be added in `hivemind.types.event` and emitted from your code; replay and telemetry can be extended to handle them.

## Adding providers

1. **Implement a provider:** In `hivemind/providers/`, create a class that implements the base provider interface (e.g. `generate(model_name, prompt) -> str`). See `openai.py`, `anthropic.py`, `gemini.py` for examples.
2. **Register in the router:** In `hivemind/providers/router.py`, add a mapping from model name (or prefix) to your provider. Optionally support a `provider:model` format by parsing the model string.
3. **Config:** Document any new env vars or TOML keys (e.g. `[my_provider]`) in `config.py` and in the docs.

## Tests

- **Run all:** `uv run python -m pytest tests/ -v`
- **Run a subset:** `uv run python -m pytest tests/test_swarm.py tests/test_planner.py -v`
- **Coverage (if configured):** `uv run pytest tests/ --cov=hivemind`

Keep existing tests passing when changing runtime behavior; add tests for new tools or new public APIs.
