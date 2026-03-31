# Devsper Runtime Core

Devsper runtime is built as a modular orchestration core with bounded concurrency, dynamic DAG mutation, and event-stream-driven observability.

## Runtime Architecture Diagram

```text
User Task
   |
   v
Swarm.run()
   |
   v
Planner -> Scheduler (DAG)
   |
   v
Runtime Executor ------------------------------+
   |                                           |
   +-> RuntimeStateManager                     |
   +-> ExecutionGraph                          |
   +-> RuntimeEventStream -> EventLog -> SSE  |
   +-> TaskRunner                              |
         +-> AgentRunner (optional stream-tool loop)
               +-> Agent
               +-> ToolRunner / tools.tool_runner
```

## Core Components

- `swarm/swarm.py`
  - Public entrypoint (`Swarm`), config/wiring, planning and execution bootstrap.
- `runtime/executor.py`
  - Event-driven scheduler loop, bounded parallel execution, cancellation propagation, dynamic task injection.
- `runtime/state_manager.py`
  - Concurrency-safe task state transitions and runtime DAG mutation entrypoint.
- `runtime/execution_graph.py`
  - Execution graph with lineage, edges, attempts, and status transitions.
- `runtime/planner.py`
  - Runtime wrapper for dynamic planner expansion and parent-child lineage.
- `runtime/task_runner.py`
  - Task lifecycle orchestration with scoped retries and fallback model handling.
- `runtime/agent_runner.py`
  - Async agent wrapper with optional streaming tool invocation loop.
- `runtime/tool_runner.py`
  - Parallel tool scheduler with bounded concurrency, dependency-aware batching, timeout, and cancellation.
- `runtime/event_stream.py`
  - In-process stream with queue backpressure policy (drop-oldest on overflow).
- `runtime/retry.py`
  - Retry scopes (`tool`, `agent`, `task`, `model_fallback`) and backoff policies.

## Execution Lifecycle

1. `Swarm.run()` creates root task, plans subtasks, and builds scheduler DAG.
2. Executor emits `EXECUTOR_STARTED` and begins bounded task dispatch.
3. Ready tasks transition to running through `RuntimeStateManager`.
4. `TaskRunner` executes with scoped retries.
5. `AgentRunner` may invoke tools (normal or streaming tool loop).
6. Task completion/failure updates scheduler + execution graph.
7. Adaptive mode can inject follow-up tasks at runtime.
8. Executor emits `EXECUTOR_FINISHED` and `RUN_COMPLETED`.

## Tool Calling Flow

1. Agent determines tool intent from model output.
2. Tool calls are parsed and scheduled.
3. `ToolRunner.run_many(...)` executes calls in parallel with:
   - `max_concurrency` semaphore
   - dependency constraints (`depends_on`)
   - per-call timeouts
   - cancellation checks
4. Results are isolated per call and fed back into agent loop.

## Planner Flow

1. Initial decomposition by `swarm/planner.py`.
2. Runtime execution completes a task.
3. `RuntimePlanner.expand(...)` optionally creates follow-up tasks.
4. `RuntimeStateManager.add_tasks(...)` mutates DAG safely.
5. `ExecutionGraph` records lineage from parent task.

## Concurrency Model

- Bounded executor workers (`worker_count`).
- Bounded tool concurrency (`ToolRunner` semaphore).
- Queue backpressure in event streaming (`max_queue_size` with controlled dropping).
- Cooperative pause/resume and cancellation propagation across runtime loops.
- Lock-guarded scheduler mutations via `RuntimeStateManager`.

## Distributed Runtime Architecture

```text
Controller
   |
   v
Worker Pool
   |
   v
Worker Runtime
   |
   v
Runtime Executor
   |
   v
Agent Pool
   |
   v
Tool Runner
```

- `distributed/controller.py`
  - Worker registry, health state, load-aware assignment, reassignment hooks.
- `distributed/worker_runtime.py`
  - Worker-local runtime composition: `Executor`, `AgentPool`, `ModelRouter`, `ToolRunner`.
- Existing multi-node transport/control remains in `nodes/controller.py` and `nodes/worker.py`.

## Worker Lifecycle

1. Worker registers with controller.
2. Controller assigns tasks based on health and load.
3. Worker executes task locally through runtime executor stack.
4. Worker returns completion/failure.
5. Controller updates worker/task state and reassigns on failure.

## Controller Lifecycle

1. Track worker registration and health.
2. Assign ready tasks using load-aware strategy.
3. Handle failures and perform retry/reassignment.
4. Maintain global execution progress via event/log channels.

## Agent Pool

- `AgentPool` manages reusable agent instances per worker.
- Supports `acquire_agent`, `release_agent`, `run_agent`, and `run_parallel`.
- Enables worker-local, concurrent, reuse-based execution.

## Speculative Execution

- `SpeculativePlanner` predicts likely successor tasks.
- Executor marks/schedules speculative tasks early.
- Unused speculative branches can be cancelled on dependency failure.

## HITL Flow

1. Agent indicates human input is required.
2. Runtime emits HITL/clarification event.
3. Task pauses until response or timeout.
4. Execution resumes or fails based on response policy.
