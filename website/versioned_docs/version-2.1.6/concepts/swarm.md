---
title: Swarm Runtime
---

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
   - **Strategy selection (v1):** A strategy selector picks a strategy (research, code analysis, data science, document, experiment). If the strategy returns a DAG of tasks, the planner uses it; otherwise it calls the LLM to produce a numbered list of steps.
   - Parses the list (or uses the strategy DAG) into subtasks with dependencies.
   - Emits `task_created` for each subtask and returns the list.

2. **Scheduler**
   - Receives all subtasks via `add_tasks`.
   - Builds a DAG (no cycles).
   - Exposes `get_ready_tasks()`: tasks that are PENDING and whose dependencies are all COMPLETED.

3. **Executor**
   - Loop: while not `scheduler.is_finished()`, get ready tasks, run each in a worker (with a concurrency limit), then `mark_completed(task_id)`.
   - Each "run" is delegated to an **Agent**.
   - If adaptive planning is enabled, the planner can add new tasks after a task completes.

4. **Agent runtime**
   - For one task: build prompt (task description + optional memory context + optional tools list).
   - Call LLM; if tools are enabled, parse tool calls, run tools via the tool runner, append results to the conversation, and repeat until the agent returns a final answer.
   - Set `task.result` and emit `task_completed`.

## Running a Swarm

```python
from devsper import Swarm

swarm = Swarm(config="devsper.toml")
results = swarm.run("Analyze diffusion models and write a one-page summary.")
```
