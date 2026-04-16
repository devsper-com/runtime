# Graph Engine

The self-evolving DAG engine is the performance-critical core of devsper. It runs a directed acyclic graph of tasks that can mutate while executing — agents can inject new nodes, prune branches, and speculate on future work without pausing the graph.

---

## Actor model

No shared mutable state. All graph access goes through message-passing:

```
GraphActor  ←mpsc→  ExecutorActor  ←mpsc→  AgentActor(s)
     ↓                                           ↓
  EventLog                               MutationRequest
     ↓
  BusActor  ←broadcast→  Peers / TUI
```

**GraphActor** is the single writer. It owns the `petgraph::DiGraph` and processes all mutations serially from a bounded mpsc channel. This eliminates lock contention on the hot path.

**ExecutorActor** holds a `GraphHandle` (clone-safe, async). It polls `get_ready()` in a tight loop, claims nodes atomically, and spawns Tokio tasks per agent.

**AgentActor** calls the LLM, runs tools, and may return `GraphMutation` requests alongside its result. These are forwarded back to the `GraphActor`.

**BusActor** receives `GraphEvent` messages via a separate channel and publishes them to all subscribers (in-memory broadcast, Redis, or Kafka).

---

## Node state machine

```
Pending ──────────────────► Ready ──► Running ──► Completed
                                                 ↘ Failed
                                                 ↘ Abandoned

Speculative path:
Pending ──► Speculative ──► Confirmed ──► Running ──► Completed
                         ↘ Discarded ──► Abandoned
```

| Transition         | Trigger                                      |
|--------------------|----------------------------------------------|
| Pending → Ready    | All `depends_on` nodes reach `Completed`.    |
| Ready → Running    | Executor claims the node (atomic pop).       |
| Running → Completed| Agent returns successfully.                  |
| Running → Failed   | Agent returns an error.                      |
| Any → Abandoned    | Upstream failure propagates; or Discarded.   |
| Pending → Speculative | `MarkSpeculative` mutation applied.       |
| Speculative → Confirmed | `ConfirmSpeculative` mutation applied. |
| Speculative → Discarded | `DiscardSpeculative` mutation applied. |

---

## Mutation pipeline

Every mutation goes through the same five-step pipeline:

```
1. Receive MutationRequest via mpsc
2. MutationValidator — DFS cycle check on cloned graph (O(V+E))
3. Atomic apply to petgraph::DiGraph
4. Frontier recomputation — ready-set scan (O(nodes))
5. GraphEvent appended to EventLog
6. ExecutorActor notified via mpsc ping
```

**Cycle detection:** The validator clones the DiGraph, applies the proposed edge(s), and calls `petgraph::algo::is_cyclic_directed`. If a cycle is detected, the mutation is rejected with a `MutationRejected` event. The graph is never left in an invalid state.

**Atomicity:** The validator and apply happen in the same `GraphActor` task loop iteration. There is no window where the graph is partially applied.

---

## Mutations reference

| Mutation             | Description                                              |
|----------------------|----------------------------------------------------------|
| `AddNode`            | Add a new `Pending` node with a given `NodeSpec`.        |
| `AddEdge`            | Add a dependency edge from → to. Cycle-checked.          |
| `RemoveEdge`         | Remove an existing edge. Triggers frontier recompute.    |
| `SplitNode`          | Replace a node with multiple parallel nodes.             |
| `InjectBefore`       | Insert a node upstream of an existing node.              |
| `PruneSubgraph`      | Remove a node and all its transitive dependents (BFS).   |
| `MarkSpeculative`    | Mark nodes as `Speculative` — prefetch begins.           |
| `ConfirmSpeculative` | Confirm speculative nodes → transition to `Running`.     |
| `DiscardSpeculative` | Discard speculative nodes → transition to `Abandoned`.   |

---

## EventLog

The `EventLog` is an append-only `Vec<GraphEvent>` stored in the `GraphActor`. Every state change produces an event:

```rust
pub enum GraphEvent {
    NodeAdded       { id: NodeId, spec: NodeSpec, ts: u64 },
    NodeReady       { id: NodeId, ts: u64 },
    NodeStarted     { id: NodeId, ts: u64 },
    NodeCompleted   { id: NodeId, result: serde_json::Value, ts: u64 },
    NodeFailed      { id: NodeId, error: String, ts: u64 },
    NodeAbandoned   { id: NodeId, ts: u64 },
    EdgeAdded       { from: NodeId, to: NodeId, ts: u64 },
    EdgeRemoved     { from: NodeId, to: NodeId, ts: u64 },
    MutationApplied { mutation: GraphMutation, ts: u64 },
    MutationRejected{ mutation: GraphMutation, reason: String, ts: u64 },
    SnapshotTaken   { state: GraphSnapshot, ts: u64 },
    RunStarted      { run_id: RunId, ts: u64 },
    RunCompleted    { run_id: RunId, ts: u64 },
    RunFailed       { run_id: RunId, error: String, ts: u64 },
}
```

### Snapshots

Every 1000 events (configurable), the `GraphActor` serializes the full `GraphSnapshot` (node states + edges + results) into the `EventLog` as a `SnapshotTaken` event.

On recovery (coordinator restart or re-election), the new leader:
1. Finds the latest `SnapshotTaken` event.
2. Deserializes the `GraphSnapshot` as the starting state.
3. Replays all events after the snapshot to bring the graph current.
4. Resumes the executor from the reconstructed frontier.

---

## Frontier computation

The **ready-set** is the set of `Pending` nodes where every `depends_on` predecessor is `Completed`.

The `GraphActor` maintains the ready-set incrementally. After every state change:

```
for each Pending node N:
    if all predecessors of N are Completed:
        N → Ready
        add N to ready_set
```

The executor calls `get_ready()` to atomically pop from this set.

This scan is O(nodes) per state change. For graphs with thousands of nodes, this is fast — petgraph's adjacency list representation is cache-friendly.

---

## Speculative execution

Speculative nodes allow agents to prefetch LLM context for likely future tasks, eliminating sequential latency on high-confidence prediction paths.

```
1. Agent predicts next tasks with high confidence
2. Agent sends MarkSpeculative { nodes: [id1, id2] }
3. GraphActor transitions those nodes to Speculative state
4. Executor starts prefetching LLM context for Speculative nodes
5a. If prediction correct: ConfirmSpeculative → nodes enter Running immediately
5b. If prediction wrong:   DiscardSpeculative → nodes enter Abandoned, results dropped
```

The net effect: a correctly-predicted speculative node adds zero latency to the critical path. The cost of a wrong prediction is the prefetch overhead, which is bounded by the node's timeout.

---

## Performance targets

| Metric                         | Target          |
|--------------------------------|-----------------|
| Graph mutations/sec            | ≥ 1,000         |
| Nodes in a single graph        | ≥ 10,000        |
| Cycle check latency (10k nodes)| < 1 ms          |
| Frontier recompute (10k nodes) | < 5 ms          |
| EventLog append                | < 1 µs          |

Run benchmarks:

```bash
cargo bench -p devsper-graph
```
