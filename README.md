# Hivemind

**Orchestrate distributed swarms of AI agents that collaboratively solve complex tasks.**

Hivemind is an open-source framework for running coordinated multi-agent systems locally. Instead of a single LLM or sequential chains, it uses a **swarm execution model**: tasks are decomposed into subtasks, executed by multiple agents in parallel, and coordinated through a scheduler and dependency graph.

---

## Why Hivemind?

Large reasoning tasks don’t fit single-pass prompts. You run into:

- Context window limits  
- Sequential bottlenecks  
- No real parallelism  
- Hard-to-debug, opaque reasoning  

Existing tools support chaining and tools, but not **many agents at once** with clear scheduling, dependencies, and observability.

Hivemind gives you a small orchestration layer to:

- **Decompose** tasks into subtasks  
- **Run** independent subtasks in parallel  
- **Respect** task dependencies  
- **Observe** behavior via a structured event log  
- **Aggregate** results into a final output  

All of this runs **locally**, with minimal setup and no distributed cluster.

---

## Core Concepts

| Concept | Description |
|--------|-------------|
| **Agent** | A stateless reasoning worker that takes a task description and returns an output. |
| **Planner** | Decomposes a high-level task into a list of subtasks. |
| **Task graph** | A DAG of subtasks; a task runs only after its dependencies complete. |
| **Executor** | Schedules and runs tasks, assigning ready work to available workers. |
| **Worker pool** | Manages concurrency and multiple agents running in parallel. |
| **Event log** | Append-only log of system actions (`task_created`, `task_started`, `agent_invoked`, `task_completed`, etc.) for inspection and debugging. |

---

## Execution Flow

1. **Submit** a high-level task.  
2. **Plan** — the planner breaks it into subtasks.  
3. **Build** a dependency graph from those subtasks.  
4. **Schedule** — the executor finds tasks whose dependencies are done.  
5. **Execute** — workers run ready tasks in parallel.  
6. **Collect** — outputs are recorded and passed to dependents.  
7. **Finish** when every node in the graph has completed.

---

## Installation

Requires **Python 3.12+**. [uv](https://docs.astral.sh/uv/) is recommended:

```bash
# Clone the repository
git clone https://github.com/your-org/hivemind.git
cd hivemind

# Create environment and install (with uv)
uv sync
```

Or with pip:

```bash
pip install -e .
```

---

## Project Structure

```
hivemind/
├── hivemind/
│   ├── types/          # Core data models (Task, Event, Swarm)
│   ├── utils/          # Utilities (e.g. event logging)
│   └── ...
├── pyproject.toml
└── README.md
```

The codebase is split by responsibility: agents, swarm orchestration, runtime, and utilities. Examples live in the repo to show typical workflows.

---

## Example Use Cases

- **Research synthesis** — Split a topic into sub-questions, run agents in parallel, merge into a report.  
- **Document summarization** — Chunk documents, summarize in parallel, combine.  
- **Codebase analysis** — Different agents analyze different parts of the repo; aggregate into an architecture summary.  
- **Information extraction** — Parallel processing of large datasets to extract structured knowledge.

---

## Design Principles

- **Minimal** — Small set of primitives; no unnecessary features.  
- **Extensible** — Swap planners, schedulers, and execution strategies without changing the core.  
- **Observable** — Structured event log for inspection and debugging.  
- **Parallel-first** — Architecture built for concurrent agent execution.  
- **Local-first** — v0.1 runs entirely on your machine; no cluster or external orchestration required.

---

## Non-Goals (v0.1)

Out of scope for the initial release:

- Distributed execution across multiple machines  
- Persistent vector DBs or long-term memory  
- Rich agent-to-agent communication protocols  
- Production auth/security  
- UI dashboards  
- Tight coupling to external orchestration frameworks  

These may be considered in later versions.

---

## Roadmap

The first release establishes the core architecture. Possible future directions:

- Distributed cluster execution  
- Replay and execution visualization  
- Persistent memory and knowledge graphs  
- Agent communication protocols  
- Adaptive planning and advanced scheduling  

---

## License

See the repository for license information.

---

## Contributing

Contributions are welcome. Please open an issue or PR; see the repo for guidelines.
