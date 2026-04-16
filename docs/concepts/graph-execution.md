# Graph Execution

Devsper executes workflows as a **self-evolving directed acyclic graph (DAG)**. Unlike static pipeline systems, the graph can mutate at runtime: agents can add nodes, split tasks, prune dead branches, or mark future work as speculative. This page explains how the graph engine works.

---

## Actor model

The graph is owned exclusively by a single `GraphActor` running in a dedicated Tokio task. No other component touches the graph data structure directly. All interactions go through a `GraphHandle` (a typed message-passing facade).

```
┌─────────────────────────────────────────────────────────────────┐
│  Executor tasks (N concurrent)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ AgentTask-1  │  │ AgentTask-2  │  │ AgentTask-N  │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │ GraphHandle      │                  │                  │
│         └──────────────────┴──────────────────┘                 │
│                             │ mpsc channel                      │
│                    ┌────────▼────────┐                          │
│                    │  GraphActor     │                          │
│                    │  (single writer)│                          │
│                    │  petgraph DiGraph│                         │
│                    └────────┬────────┘                          │
│                             │ mpsc channel (GraphEvent stream)  │
│                    ┌────────▼────────┐                          │
│                    │  EventLog       │                          │
│                    │  (append-only)  │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

`GraphActor::new()` returns a triple: `(actor, handle, event_receiver)`. The caller spawns `tokio::spawn(actor.run())` and distributes clones of `handle` to executor tasks.

---

## Node state machine

```
                    ┌─────────┐
              ┌─────│ Pending │─────┐
              │     └─────────┘     │
              │ (all deps done)      │ MarkSpeculative
              ▼                     ▼
           ┌───────┐          ┌─────────────┐
           │ Ready │          │ Speculative │
           └───┬───┘          └──────┬──────┘
               │ claim()             │ Confirm / Discard
               ▼                     ▼
           ┌─────────┐         ┌──────────┐
           │ Running │         │ Pending  │ (back to normal)
           └────┬────┘         │ Abandoned│
                │              └──────────┘
          ┌─────┴──────┐
          ▼            ▼
     ┌─────────┐  ┌────────┐  ┌───────────┐
     │Completed│  │ Failed │  │ Abandoned │
     └─────────┘  └────────┘  └───────────┘
```

- **Pending** — created, waiting for dependencies
- **Ready** — all dependencies completed, eligible for execution
- **Running** — claimed by an executor task
- **Completed** — agent returned successfully
- **Failed** — agent returned an error
- **Abandoned** — pruned by a `PruneSubgraph` or `DiscardSpeculative` mutation
- **Speculative** — future node, held back from the ready set until confirmed

---

## Mutation pipeline

When an agent (or external caller) submits a `GraphMutation` via `handle.mutate()`, the pipeline runs in this order:

```
GraphHandle.mutate(mutation)
    │
    ▼  mpsc send
GraphActor receives ActorMessage::Mutate
    │
    ├─ 1. Validation (MutationValidator)
    │       clone graph + DFS cycle check
    │       if invalid → emit MutationRejected + return Err
    │
    ├─ 2. Apply mutation
    │       modify nodes HashMap + petgraph DiGraph
    │       emit structural events (NodeAdded, EdgeAdded, etc.)
    │
    ├─ 3. Frontier recompute
    │       scan all Pending nodes
    │       move to ready_set where all depends_on are Completed
    │
    ├─ 4. Event log append
    │       EventLog.append(MutationApplied { mutation, ts })
    │
    └─ 5. Notify executor
            try_send on event channel (non-blocking, drops if slow)
```

The response to the caller is sent synchronously after validation. The caller sees either `Ok(())` (applied) or `Err(reason)` (rejected).

---

## The 9 mutation variants

### AddNode

Adds a new task node to the graph. Edges declared in `spec.depends_on` are wired automatically.

```
Use case: planner agent injects subtasks based on the goal decomposition.
```

### AddEdge

Creates a dependency edge between two existing nodes without adding new nodes.

```
Use case: agent discovers that task B should only run after task C completes,
          even though both were defined statically.
```

### RemoveEdge

Removes a dependency edge. Makes `to` node potentially ready earlier.

```
Use case: agent determines a dependency is unnecessary and can be relaxed.
```

### SplitNode

Abandons a node and replaces it with multiple new nodes. The original node is marked Abandoned.

```
Use case: planner receives a task too large to handle atomically and
          decomposes it into parallel sub-tasks.
```

### InjectBefore

Inserts a new node immediately before an existing node, wiring `new → before`.

```
Use case: agent discovers it needs a preprocessing step before the next
          task can proceed (e.g., fetch data before analysis).
```

### PruneSubgraph

Abandons a node and all its descendants (BFS over outgoing edges).

```
Use case: agent determines an entire branch of work is no longer relevant
          (e.g., a research path turned out to be a dead end).
```

### MarkSpeculative

Moves nodes from Pending to Speculative, removing them from the ready set.

```
Use case: prefetch work that may not be needed, holding it until
          a condition is checked (see ConfirmSpeculative / DiscardSpeculative).
```

### ConfirmSpeculative

Moves Speculative nodes back to Pending, re-admitting them to the ready set.

```
Use case: the condition check passed — proceed with the speculative work.
```

### DiscardSpeculative

Abandons Speculative nodes entirely. They will not execute.

```
Use case: the condition check failed — discard the speculative branch.
```

---

## Speculative execution

Speculative execution lets you prefetch work without committing to it:

```
1. Agent marks future nodes as Speculative (MarkSpeculative)
   → nodes enter holding state, not scheduled

2. Agent or coordinator evaluates the condition:
   - If needed: ConfirmSpeculative → nodes return to Pending → scheduled normally
   - If not needed: DiscardSpeculative → nodes abandoned (no execution)
```

This is useful for reducing latency when you can probabilistically predict what work will be needed next, while retaining the ability to discard it cheaply.

---

## Frontier computation

After every mutation or node completion, `recompute_ready_set()` runs:

```rust
for each node in Pending state:
    if all node.depends_on are in Completed state:
        add node to ready_set
```

The `ready_set` is a `HashSet<NodeId>` maintained in the actor. `GraphHandle::get_ready()` returns a snapshot of it. Multiple executor tasks can call `get_ready()` concurrently; the actor serializes access.

The claim/execute race is handled by `GraphHandle::claim(id)`:
- Returns `true` if the node was in `ready_set` and successfully transitioned to Running
- Returns `false` if another executor already claimed it

---

## EventLog and recovery

The `EventLog` stores all `GraphEvent` values in an append-only `Vec`. Every `snapshot_interval` events (default: 1000), the actor automatically:

1. Calls `build_current_snapshot()` — full serializable state of all nodes and edges
2. Appends `SnapshotTaken { snapshot, ts }` to the log
3. Emits the snapshot event on the event channel

**Recovery path**: to restart a failed run, load the latest `GraphSnapshot` from persistent storage, restore the graph state, then replay `GraphEvent` entries appended after the snapshot timestamp. The event channel can be wired to Redis, Kafka, or any persistent store for durable runs.

---

## The 14 GraphEvent variants

| Event | Trigger |
|---|---|
| `NodeAdded` | AddNode / InjectBefore / SplitNode mutation applied |
| `NodeReady` | (reserved — ready state is implicit in frontier computation) |
| `NodeStarted` | claim() succeeded |
| `NodeCompleted` | complete() called with result |
| `NodeFailed` | fail() called with error |
| `NodeAbandoned` | PruneSubgraph, SplitNode (original), or DiscardSpeculative |
| `EdgeAdded` | AddEdge / AddNode with deps / InjectBefore |
| `EdgeRemoved` | RemoveEdge mutation applied |
| `MutationApplied` | Mutation passed validation and was applied |
| `MutationRejected` | Mutation failed validation (cycle, unknown node, etc.) |
| `SnapshotTaken` | Auto-snapshot interval reached |
| `RunStarted` | (emitted by executor on run start) |
| `RunCompleted` | All nodes terminal |
| `RunFailed` | Unrecoverable executor error |

---

## Cycle detection

`MutationValidator` prevents cycles by cloning the current petgraph `DiGraph`, applying the proposed edge(s) to the clone, then running a DFS cycle check. If a cycle is detected, the mutation is rejected before touching the live graph.

The validator is called synchronously inside the actor's message loop — no graph state is modified until validation passes.
