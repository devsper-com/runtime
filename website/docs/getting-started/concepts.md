---
title: Key Concepts
---

# Key Concepts

hivemind is built around a pipeline that decomposes tasks into a dependency graph, executes them across parallel agents, and persists results into memory and a knowledge graph. This page covers the core abstractions.

## Swarm

The `Swarm` is the top-level runtime. It owns the configuration, wires together every subsystem, and provides the public API:

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Analyze the trade-offs of microservice architectures.")
```

A single Swarm instance manages the full lifecycle of a run: planning, scheduling, execution, memory writes, and event logging.

## Tasks and the DAG

Every user request is broken into a directed acyclic graph (DAG) of **tasks**. Each task is a self-contained unit of work with explicit input/output contracts and declared dependencies. The DAG ensures that tasks run in the correct order while maximizing parallelism -- independent branches execute concurrently.

## Planner

The **Planner** is responsible for decomposing a high-level objective into a DAG of subtasks. hivemind supports multiple planning strategies:

- **LLM-based planning** -- an LLM generates the task graph given the objective and available tools.
- **Strategy-based planning** -- deterministic decomposition using predefined templates for common patterns (research, analysis, code generation).

The planner outputs a structured task graph that the scheduler consumes.

## Scheduler

The **Scheduler** maintains the DAG at runtime. It tracks task states (pending, ready, running, completed, failed), resolves dependencies, and yields the next batch of ready tasks to the executor. When a task completes, the scheduler updates the graph and releases any downstream tasks whose dependencies are now satisfied.

## Executor

The **Executor** drives the run loop. It pulls ready tasks from the scheduler, dispatches them to agents subject to a configurable concurrency limit (`workers` in `hivemind.toml`), and collects results. The executor handles retries, timeouts, and error propagation.

## Agents

**Agents** are stateless LLM workers. Each agent receives a single task, a set of available tools, and relevant context from memory. It calls the configured LLM provider, optionally invokes tools, and returns a structured result. Because agents are stateless, they can run in parallel without shared mutable state.

Supported LLM providers include OpenAI, Anthropic, Gemini, Azure, and GitHub Models.

## Tools

Agents interact with the outside world through **tools**. hivemind ships 120+ built-in tools organized by domain:

- **Research** -- web search, URL fetching, academic paper retrieval
- **Coding** -- file read/write, shell execution, linting, test runners
- **Data science** -- CSV/JSON parsing, statistical analysis, visualization
- **Filesystem** -- directory traversal, file manipulation, archive handling
- **Knowledge** -- memory queries, knowledge graph lookups

Tools are registered in a central catalog. You can restrict which tools are available per task or per run using configuration or CLI flags.

## Memory

hivemind persists information across runs in a SQLite-backed **memory** store. Memory is divided into four types:

| Type | Purpose |
|------|---------|
| **Episodic** | Records of what happened during a run (actions, decisions, observations) |
| **Semantic** | Distilled facts and knowledge extracted from task results |
| **Research** | Raw research artifacts such as fetched documents and search results |
| **Artifact** | Generated outputs like reports, code files, and datasets |

Agents read from memory to gain context and write back to it so future runs can build on prior work.

## Knowledge Graph

The **Knowledge Graph** stores structured relationships between entities discovered during runs. Entity types include concepts, datasets, methods, people, and organizations. Relationships capture how entities relate (e.g., "method A outperforms method B on dataset C").

The knowledge graph is queryable via:

```bash
hivemind query "What methods have been compared on ImageNet?"
```

It grows incrementally across runs, forming a persistent, navigable map of everything hivemind has learned.

## Workflows

**Workflows** are TOML-defined multi-step pipelines that chain tasks with explicit dependencies and variable substitution. They are useful for repeatable processes like research pipelines, report generation, or CI-like automation.

```toml
[[workflow.steps]]
name = "gather"
task = "Collect sources on {topic}."

[[workflow.steps]]
name = "synthesize"
task = "Synthesize findings into a report."
depends_on = ["gather"]
```

See the [Workflows](/docs/concepts/workflows) documentation for the full specification.

## Plugins

The **plugin system** allows external packages to register additional tools, planners, or memory backends. Plugins use Python entry points, so installing a package is enough to make its extensions available:

```bash
pip install hivemind-plugin-jira
```

hivemind discovers and loads plugins automatically at startup via the plugin registry.

## Events

Every action during a run is recorded as an **event** in a JSONL log. Events capture task state transitions, tool invocations, LLM calls, memory writes, and errors. The event log enables:

- **Replay** -- re-examine exactly what happened during a run.
- **Telemetry** -- aggregate metrics like token usage, latency, and error rates.
- **Debugging** -- trace failures back to the specific agent and tool call.

Event logs are stored per-run and can be inspected with `hivemind runs show <run-id>`.

## Next steps

- [Installation](/docs/getting-started/installation) -- set up hivemind
- [Quickstart](/docs/getting-started/quickstart) -- run your first task
- [Configuration](/docs/configuration) -- full `hivemind.toml` reference
- [Tools](/docs/tools) -- browse the built-in tool catalog
