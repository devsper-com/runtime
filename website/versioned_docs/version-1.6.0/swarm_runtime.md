# Swarm Runtime

## Task Lifecycle

Tasks move through a small set of states and events:

1. **task_created** — The planner (or adaptive step) has created a new task and added it to the scheduler. The task is **PENDING**.
2. **task_started** — The executor has assigned the task to an agent; the agent has begun work. The task is **RUNNING**.
3. **task_completed** — The agent finished and produced a result. The task is **COMPLETED** and its result is stored.

If something goes wrong, **task_failed** can be used; the scheduler may still mark the task completed or leave it for retry depending on implementation.

## Flow: Planner → Scheduler → Executor → Agent

1. **Planner**  
   - Receives the root task.  
   - **Strategy selection (v1):** A strategy selector (keyword heuristics, optional embedding/LLM) picks a strategy (research, code analysis, data science, document, experiment). If the strategy returns a DAG of tasks, the planner uses it; otherwise it calls the LLM to produce a numbered list of steps.  
   - Parses the list (or uses the strategy DAG) into subtasks with dependencies.  
   - Emits `task_created` for each subtask and returns the list.

2. **Scheduler**  
   - Receives all subtasks via `add_tasks`.  
   - Builds a DAG (no cycles).  
   - Exposes `get_ready_tasks()`: tasks that are PENDING and whose dependencies are all COMPLETED.

3. **Executor**  
   - Loop: while not `scheduler.is_finished()`, get ready tasks, run each in a worker (with a concurrency limit), then `mark_completed(task_id)`.  
   - Each “run” is delegated to an **Agent**.  
   - If adaptive planning is enabled, the planner can add new tasks after a task completes; the scheduler accepts them and they enter the same loop.
   - **Fast path (v1.6):** Semantic task cache (embedding-based lookup), model complexity routing (simple → fast model, complex → quality model), and **streaming DAG** unblocking (dependents start as soon as a task completes). See [Configuration](configuration#cache-v16) for `[cache]` and `[models]` fast/quality.

4. **Agent runtime**  
   - For one task: build prompt (task description + optional memory context + optional tools list).  
   - Call LLM; if tools are enabled, parse tool calls, run tools via the tool runner, append results to the conversation, and repeat until the agent returns a final answer.  
   - Set `task.result` and emit `task_completed`.  
   - **Parallel tools (v1.6):** When multiple tool calls appear in one turn, independent tools run in parallel (config `swarm.parallel_tools`; bypass with `HIVEMIND_DISABLE_PARALLEL_TOOLS=1`).

## Running a Swarm (Code Snippets)

**With config file (v1):**

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Analyze diffusion models and write a one-page summary.")
# results: dict[task_id, result_text]
```

**Minimal (explicit parameters):**

```python
from hivemind import Swarm

swarm = Swarm(
    worker_count=4,
    worker_model="gpt-4o-mini",
    planner_model="gpt-4o-mini",
)
results = swarm.run("Analyze diffusion models and write a one-page summary.")
# results: dict[task_id, result_text]
```

**With event log, memory, and tools:**

```python
from hivemind.swarm.swarm import Swarm
from hivemind.utils.event_logger import EventLog
from hivemind.memory.memory_router import MemoryRouter
from hivemind.memory.memory_store import get_default_store
from hivemind.memory.memory_index import MemoryIndex

event_log = EventLog()
memory_router = MemoryRouter(
    store=get_default_store(),
    index=MemoryIndex(get_default_store()),
    top_k=5,
)
swarm = Swarm(
    worker_count=4,
    worker_model="gpt-4o-mini",
    planner_model="gpt-4o-mini",
    event_log=event_log,
    memory_router=memory_router,
    use_tools=True,
    store_swarm_memory=True,
)
results = swarm.run("Summarize recent research on swarm intelligence.")
for task_id, text in results.items():
    print(f"--- {task_id} ---")
    print(text[:500])
```

**Accessing completed tasks after a run:**

```python
completed = swarm.last_completed_tasks
for task in completed:
    print(task.id, task.description, (task.result or "")[:200])
```

Events are written to the path in `event_log.log_path` (e.g. for replay or telemetry).

## Map-reduce (v1)

The swarm runtime includes a **map-reduce** primitive for batch processing over a dataset without using the task DAG:

```python
from hivemind import Swarm

swarm = Swarm(worker_count=4)
# Process each item in parallel, then reduce
result = swarm.map_reduce(
    dataset=[1, 2, 3, 4, 5],
    map_fn=lambda x: x * 2,
    reduce_fn=sum,
)
# result == 30
```

- **Flow:** The dataset is processed in parallel (up to `worker_count` items at a time); each item is passed to `map_fn`; results are collected and passed once to `reduce_fn`.
- **Use case:** Batch embedding, batch file processing, or any embarrassingly parallel workload that ends in a single aggregation. The same asyncio/semaphore pattern as the executor is used.
