# FAQ

## What makes devsper different from LangChain?

- **Focus:** devsper is a **swarm runtime**: it decomposes one high-level task into a DAG of subtasks and runs them with dependency-aware scheduling and configurable parallelism. LangChain is a broad framework for chains, agents, and tool use; it doesn’t center on this “plan → schedule → execute” swarm model.
- **Execution model:** devsper has a built-in **Planner → Scheduler → Executor** pipeline and a single entrypoint (`Swarm().run(...)`). You get parallel execution of independent subtasks and optional adaptive planning without building that yourself.
- **Ecosystem:** devsper can use LangChain (or other libs) under the hood for LLM calls or tools, but the value is in the swarm orchestration, event log, memory router, and knowledge graph wired for multi-step, multi-agent runs.

## How does swarm execution work?

1. You call `Swarm().run("your task")`.
2. The **Planner** uses an LLM to break the task into a small set of **subtasks** with dependencies (e.g. step 2 depends on step 1).
3. The **Scheduler** holds these in a DAG and repeatedly returns tasks whose dependencies are all completed.
4. The **Executor** runs those **ready** tasks in parallel (up to a worker limit), each via an **Agent** (LLM + optional tools + memory context).
5. When a task completes, the scheduler marks it done; optionally the planner adds more tasks (adaptive). This repeats until no tasks remain.
6. Results are aggregated; optionally outputs are stored in **swarm memory** and the **knowledge graph** for future runs.

See [Swarm Runtime](swarm_runtime.md) and [Architecture](architecture.md) for details.

## How do I add new tools?

1. Subclass `Tool` in `devsper.tools.base`: set `name`, `description`, `input_schema`, and implement `run(**kwargs) -> str`.
2. Call `register(MyTool())` (from `devsper.tools.registry`) so the tool is in the registry.
3. Put the module in a category under `devsper/tools/` and ensure it’s imported (e.g. in that category’s `__init__.py`).

Agents see tools when `Swarm(..., use_tools=True)`. See [Tools](tools.md) for a full example and schema rules.

## How do I store API keys?

Use the **credential store** (OS keychain) so you don’t re-enter keys and never put them in config files:

- **Store:** `devsper credentials set openai api_key` (prompts for the value).
- **Import from .env:** `devsper credentials migrate` (copies from `.env` / TOML into the keyring).
- **List (no values):** `devsper credentials list`.
- **Export for a script:** `eval "$(devsper credentials export azure)"` or `devsper credentials export azure >> .env`.

Supported providers: `openai`, `anthropic`, `github`, `gemini`, `azure`, `azure_anthropic`. See [Configuration](configuration.md#credentials-api-keys) and [CLI](cli.md#credentials).

## How do I use a config file (v1)?

- Put a **`devsper.toml`** in your project root (or use `~/.config/devsper/config.toml`). See [Configuration](configuration.md) for the full schema (`[swarm]`, `[models]`, `[memory]`, `[tools]`, `[telemetry]`, `[providers.azure]`).
- In code: `Swarm(config="devsper.toml")` loads that file and applies env overrides. You can also pass a config object from `get_config()`.
- Legacy `.devsper/config.toml` and `[default]` keys are still supported and mapped into the new schema.

## How do I run a workflow or query the knowledge graph (v1)?

- **Workflow:** Define steps in **`workflow.devsper.toml`** under `[workflow]` with `name` and `steps` (list of step descriptions). Run with `devsper workflow <name>`.
- **Knowledge graph:** Run `devsper query "your search terms"` to search entities (concepts, datasets, methods) and relationships in the graph built from memory. See [CLI](cli.md#devsper-query-query-text).

## How do I run my own models?

- **Config:** Set `worker_model` and `planner_model` in config or environment (`DEVSPER_WORKER_MODEL`, `DEVSPER_PLANNER_MODEL`). Use the model name your provider expects (e.g. `gpt-4o`, `claude-3-haiku-20240307`, `gemini-1.5-flash`).
- **Providers:** The router picks the provider from the model name. For **Azure**, set the right env vars (e.g. `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`) so GPT-style names use Azure; same idea for Azure Anthropic and Claude.
- **Custom provider:** Implement a provider that supports your API and register it in the router (see [Development](development.md#adding-providers)).

No need to change core runtime logic; configuration and the provider layer handle model selection.
