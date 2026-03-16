# Architecture

## System Architecture Diagram

```
    Planner
       ↓
    Scheduler
       ↓
    Executor
       ↓
    Agents
       ↓
    Tools
       ↓
    Memory
       ↓
    Knowledge Graph
```

## Component Overview

### Planner

- **Role:** Converts one root task into multiple subtasks with sequential (or DAG) dependencies.
- **Strategy-based planning (v1):** A **strategy selector** (keyword heuristics, optional embedding/LLM) chooses a strategy (research, code analysis, data science, document pipeline, experiment). Each strategy returns a fixed DAG of tasks (e.g. research: corpus_builder → topic_extraction → citation_graph → literature_review). If a strategy is selected and returns tasks, the planner uses that DAG; otherwise it falls back to an LLM call to break the task into steps.
- **Input:** A single `Task` (e.g. the user’s high-level goal).
- **Output:** A list of `Task` objects, each with an ID, description, and dependency list.
- **Events:** `planner_started`, `task_created` (per subtask), `planner_finished`.
- **Optional:** Adaptive planning can extend the DAG at runtime (e.g. `expand_tasks` after a task completes).

### Scheduler

- **Role:** Maintains the task DAG and determines which tasks are runnable.
- **Data structure:** Directed acyclic graph (e.g. NetworkX); nodes are task IDs, edges are dependencies.
- **API:** `add_tasks`, `get_ready_tasks`, `mark_completed`, `is_finished`, `get_results`, `get_completed_tasks`.
- **Invariant:** Only tasks whose dependencies are all completed are returned as “ready.”

### Executor

- **Role:** Drives execution until the scheduler reports all tasks completed.
- **Behavior:** In a loop, gets ready tasks, runs each via an **Agent** (with a concurrency limit, e.g. semaphore), then marks tasks completed. Optionally calls the planner to add new tasks (adaptive).
- **(v1.7) Critic:** After a task completes, if critic is enabled and the task role is in `critic_roles`, a **CriticAgent** scores the result; if it requests a retry, the task is re-queued once with a retry prompt.
- **(v1.7) Prefetcher:** When speculative execution and prefetch are enabled, the executor triggers background prefetch (memory + tool selection) for speculative tasks; the agent may receive a pre-warmed `prefetch_result`.
- **Events:** `executor_started`, then per-task agent/task events, then `executor_finished`; (v1.7) `TASK_CRITIQUED`, `PREFETCH_HIT`, `PREFETCH_MISS`.

### Agents

- **Role:** Stateless workers that execute a single task by calling an LLM (via the provider router).
- **Input:** A `Task` (description, optional dependencies context). (v1.7) Optional **message bus** (per-run pub/sub) and **prefetch_result** (pre-warmed memory + tools).
- **Output:** Text result stored on the task; optionally tools are invoked in a loop until the agent returns a final answer. (v1.7) Agents can start a response with `BROADCAST: <finding>` to publish to the message bus; the finding is stripped before storing the result.
- **Events:** `agent_started`, `task_started`, `task_completed`, `agent_finished`, and `tool_called` when tools are used; (v1.7) `AGENT_BROADCAST` when an agent broadcasts a finding.

### Tools

- **Role:** Named, schema-driven functions agents can call (e.g. read_file, codebase_indexer, store_memory).
- **Registry:** Tools register by name; the agent receives a list of tools and calls them via a simple protocol (e.g. `TOOL: name`, `INPUT: {...}`).
- **Smart tool selection (v1):** When config has `[tools] top_k > 0`, the **tool selector** embeds the task description and each tool’s name+description, computes similarity, and passes only the top-k tools to the agent. Optional `[tools] enabled` restricts to categories (e.g. research, coding, documents).
- **Plugins (v1):** External packages can register tools via the `devsper.plugins` entry point; the loader runs after built-in categories so plugin tools appear in the same registry.
- **Runner:** Validates arguments against each tool’s `input_schema`, runs the tool, and returns a string result (or error message).

### Memory

- **Role:** Persistent store and retrieval of context (episodic, semantic, research, artifact).
- **Store:** SQLite-backed; list, store, retrieve, delete.
- **Router:** Injects relevant memories into the agent prompt (e.g. top-k by embedding similarity).
- **Index:** Optional embeddings for semantic search over stored memories.

### Knowledge Graph

- **Role:** Builds and queries a graph over memory (documents, concepts, datasets, methods; edges like mentions, cites, related_to).
- **Query interface (v1):** `devsper/knowledge/query.py` provides entity search (match query text to node labels) and relationship traversal (1–2 hops). CLI: `devsper query "diffusion models"`.
- **Integration:** Can be populated from tool outputs or document pipelines and used to enrich context for later tasks.

### Configuration (v1)

- **Module:** `devsper/config/` — `config_loader.py`, `schema.py`, `defaults.py`, `resolver.py` with Pydantic models.
- **Locations:** `./devsper.toml`, `./workflow.devsper.toml`, `~/.config/devsper/config.toml`, legacy `.devsper/config.toml`.
- **Priority:** env > project config > user config > defaults. Exposed via `get_config()`; `Swarm(config="devsper.toml")` loads from file.

### Map-reduce runtime (v1)

- **Module:** `devsper/swarm/map_reduce.py` — `swarm.map_reduce(dataset, map_fn, reduce_fn)` partitions the dataset, runs `map_fn` on each item in parallel (worker pool), then runs `reduce_fn` on the collected results. Uses the same asyncio/semaphore pattern as the executor.

---

## Event System

All components emit **events** to a shared **EventLog**:

- **Event types:** e.g. `swarm_started`, `swarm_finished`, `planner_started`, `planner_finished`, `task_created`, `task_started`, `task_completed`, `task_failed`, `agent_started`, `agent_finished`, `executor_started`, `executor_finished`, `tool_called`.
- **Format:** Each event has a timestamp, type, and payload (e.g. `task_id`, `description`).
- **Persistence:** Events are appended to a JSONL file (e.g. `.devsper/events/events_<timestamp>.jsonl`).

The event log is used for **replay** and **telemetry** without changing runtime logic.

---

## Telemetry

- **Source:** Event log from a run (or a given log file).
- **Metrics:** Tasks completed/failed, average task duration, average agent latency, max concurrency, task success rate.
- **Use:** Post-run analysis and monitoring; can be emitted or logged when a swarm run finishes.

---

## Replay System

- **Input:** Path to an event log (JSONL).
- **Behavior:** Load events, sort by timestamp, and produce a step-by-step transcript (e.g. `[planner_started]`, `[task_created] task_id`, `[agent_started] task_id`, …).
- **Use:** Debugging and understanding execution order without re-running the swarm.
