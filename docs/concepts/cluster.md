# Cluster

Devsper includes a built-in peer mesh for distributing workflow execution across multiple nodes. Cluster mode uses a **Raft-lite** leader election protocol: one node acts as the coordinator (graph owner), while workers claim and execute tasks.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Cluster Mesh                                                   │
│                                                                 │
│  ┌──────────────────────────┐                                   │
│  │  Coordinator             │                                   │
│  │  (GraphActor owner)      │◄──── devsper run --cluster ...   │
│  │  role: Coordinator       │                                   │
│  │  term: N                 │                                   │
│  └──────────┬───────────────┘                                   │
│             │ ClusterMessage (graph events, task assignments)   │
│    ┌────────┴────────┐                                          │
│    │                 │                                          │
│  ┌─▼──────────────┐ ┌▼───────────────┐                         │
│  │  Worker-1      │ │  Worker-2      │                         │
│  │  role: Worker  │ │  role: Worker  │                         │
│  │  Executor      │ │  Executor      │                         │
│  └────────────────┘ └────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Node roles

### NodeRole::Coordinator

- Owns the `GraphActor` (the authoritative graph state)
- Receives run submissions
- Broadcasts `GraphEvent` stream to workers
- Responds to `VoteRequest` from candidates

### NodeRole::Worker

- Connects to coordinator on startup (Hello message)
- Polls for ready tasks via `GetReady`
- Claims tasks, executes agents locally, reports results back
- Maintains heartbeat with coordinator

### NodeRole::Candidate

- Transient state during leader election
- Has incremented its term and broadcast a `VoteRequest`
- Becomes Coordinator on receiving majority votes

---

## Raft-lite leader election

Devsper implements a simplified Raft-style election (no log replication — the EventLog snapshot mechanism handles recovery):

```
1. Worker detects coordinator heartbeat timeout
   → increments term
   → transitions to Candidate
   → broadcasts VoteRequest { term, candidate_id }

2. Each peer receiving VoteRequest:
   → grants vote if request.term > current_term
   → sends VoteResponse { term, granted }

3. Candidate with majority votes:
   → broadcasts LeaderElected { leader_id, term }
   → all peers update role accordingly

4. New coordinator:
   → loads latest GraphSnapshot from persistent storage (or starts fresh)
   → resumes graph execution
```

**Term tracking**: each node tracks the current election term. Votes are only granted for terms strictly greater than the node's current term, preventing split votes from older election rounds.

---

## Graph event replication

The coordinator streams `GraphEvent` values to all connected workers via `ClusterMessage::GraphEvent`. Workers maintain a local read-only view of the graph sufficient for claiming tasks.

When a worker completes a task, it sends `ClusterMessage::TaskResult { node_id, result }` to the coordinator, which calls `handle.complete()` on the GraphActor.

---

## Failure recovery

**Worker failure**: if a worker dies mid-execution, the coordinator detects the missing heartbeat and marks the node as `Failed` (triggering re-scheduling). The task returns to `Pending` and is re-claimed by another worker.

**Coordinator failure**: when workers detect a coordinator heartbeat timeout:
1. Election is triggered (see Raft-lite above)
2. The new coordinator loads the most recent `GraphSnapshot`
3. It replays `GraphEvent` entries from the EventLog that occurred after the snapshot
4. Execution resumes from the recovered state

---

## Starting a cluster

### Bootstrap the coordinator

```bash
# On the first node (becomes coordinator by default — no --join flag)
devsper peer --listen 0.0.0.0:7000
```

The node starts in Worker role, then immediately calls `become_coordinator()` since there are no known peers.

### Join workers

```bash
# On each additional node
devsper peer --listen 0.0.0.0:7001 --join coordinator-host:7000
devsper peer --listen 0.0.0.0:7002 --join coordinator-host:7000
```

Each worker sends a `Hello { address, capabilities }` message to the coordinator, which registers it in the `WorkerRegistry`.

### Submit a run to the cluster

```bash
devsper run workflow.devsper --cluster coordinator-host:7000 --input key=value
```

The run is submitted to the coordinator, which owns the graph and dispatches tasks to workers.

---

## Cluster configuration

| Config field | Default | Description |
|---|---|---|
| `listen_address` | `0.0.0.0:7000` | TCP address for this node |
| `known_peers` | `[]` | Initial peer addresses (from `--join`) |
| `heartbeat_interval_ms` | `1000` | How often to send heartbeats |
| `heartbeat_timeout_ms` | `5000` | Missing-heartbeat deadline before election |

---

## ClusterMessage types

Messages exchanged between peers:

| Message | Direction | Purpose |
|---|---|---|
| `Hello { address, capabilities }` | Worker → Coordinator | Register on join |
| `Heartbeat { ts }` | Bidirectional | Liveness check |
| `VoteRequest { term, candidate_id }` | Candidate → all | Request vote |
| `VoteResponse { term, granted }` | Peer → Candidate | Cast vote |
| `LeaderElected { leader_id, term }` | New coordinator → all | Election result |
| `GraphEvent { event }` | Coordinator → workers | Replicate graph changes |
| `TaskResult { node_id, result }` | Worker → Coordinator | Report completion |

---

## Bus configuration for clustering

Cross-node event delivery requires a shared message bus:

**Redis bus** (recommended for clusters up to ~50 nodes):

```bash
export DEVSPER_BUS=redis
export REDIS_URL=redis://redis-host:6379
devsper peer --listen 0.0.0.0:7000
```

**Kafka bus** (at-least-once delivery, large clusters):

```bash
export DEVSPER_BUS=kafka
export KAFKA_BROKERS=kafka-host:9092
devsper peer --listen 0.0.0.0:7000
```

**Memory bus** is single-process only and cannot span cluster nodes.

---

## WorkerRegistry

The coordinator maintains a `WorkerRegistry` that tracks:

- Registered peer info (`id`, `address`, `role`, `capabilities`)
- Last heartbeat timestamp per peer
- Stale peer detection (peers not seen within `heartbeat_timeout_ms` are considered dead)

```rust
// Internal API
registry.register(peer_info).await;
registry.heartbeat(&node_id).await;
registry.all_peers().await;           // all known peers
registry.active_peers().await;        // peers with recent heartbeats
```
