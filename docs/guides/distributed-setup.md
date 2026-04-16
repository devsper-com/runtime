# Distributed Setup

devsper nodes form a cluster via a Raft-lite peer mesh. The coordinator holds the `GraphActor` and dispatches tasks to workers. All nodes replicate the `EventLog`, so any node can take over if the coordinator fails.

---

## Single-node (default)

No setup needed. `devsper run` runs everything in-process.

```bash
devsper run workflow.devsper
```

---

## Multi-node cluster

### Step 1 — Start the coordinator

The first node without `--join` becomes the coordinator:

```bash
# Terminal 1 — coordinator
devsper peer --listen 0.0.0.0:7000
```

Output:
```
[info] Starting peer node
[info] No join address — becoming coordinator
[info] Listening on 0.0.0.0:7000
```

### Step 2 — Add worker nodes

```bash
# Terminal 2 — worker 1
devsper peer --join 10.0.0.1:7000 --listen 0.0.0.0:7001

# Terminal 3 — worker 2
devsper peer --join 10.0.0.1:7000 --listen 0.0.0.0:7002
```

### Step 3 — Submit a run

```bash
devsper run workflow.devsper \
  --cluster 10.0.0.1:7000 \
  --input repo_url=https://github.com/example/repo
```

The coordinator receives the workflow, builds the graph, and distributes ready tasks to workers.

---

## Redis bus (recommended for multi-node)

Switch from the default in-memory bus to Redis for cross-node event streaming:

```bash
# All nodes must share the same Redis instance
export DEVSPER_BUS=redis
export REDIS_URL=redis://10.0.0.100:6379

# Coordinator
devsper peer --listen 0.0.0.0:7000

# Workers
devsper peer --join 10.0.0.1:7000 --listen 0.0.0.0:7001
```

Redis pub/sub delivers `GraphEvent` messages to all peers in real time, enabling the TUI to connect to any node and see the full event stream.

---

## Kafka bus (durable)

For at-least-once event delivery and persistent event logs:

```bash
export DEVSPER_BUS=kafka
export KAFKA_BROKERS=10.0.0.100:9092
export KAFKA_TOPIC=devsper-events   # default

devsper peer --listen 0.0.0.0:7000
```

Kafka consumer groups ensure each event is processed exactly once per consumer. Useful when you need event durability across cluster restarts.

---

## Coordinator failure and recovery

If the coordinator fails:

1. Workers detect the missing heartbeat (configurable timeout, default 5s).
2. A worker begins an election by incrementing the term and broadcasting `VoteRequest`.
3. Workers grant votes if the candidate has a higher term.
4. The winner broadcasts `LeaderElected` and transitions to coordinator.
5. The new coordinator loads the last `GraphSnapshot` from the `EventLog` and replays tail events.
6. In-flight tasks are re-queued from the last `Running` → `Pending` checkpoint.

No manual intervention required. The cluster self-heals within one election timeout.

---

## Worker drain

To gracefully remove a worker:

```bash
# Stop the peer process — it finishes in-flight tasks before shutting down
kill -TERM <pid>
```

The coordinator detects the heartbeat gap and redistributes pending tasks to remaining workers.

---

## Docker Compose example

```yaml
version: "3.9"
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]

  coordinator:
    image: devsper:latest
    command: peer --listen 0.0.0.0:7000
    environment:
      DEVSPER_BUS: redis
      REDIS_URL: redis://redis:6379
    ports: ["7000:7000"]
    depends_on: [redis]

  worker1:
    image: devsper:latest
    command: peer --join coordinator:7000 --listen 0.0.0.0:7001
    environment:
      DEVSPER_BUS: redis
      REDIS_URL: redis://redis:6379
    depends_on: [coordinator]

  worker2:
    image: devsper:latest
    command: peer --join coordinator:7000 --listen 0.0.0.0:7002
    environment:
      DEVSPER_BUS: redis
      REDIS_URL: redis://redis:6379
    depends_on: [coordinator]
```

Submit a run:

```bash
devsper run workflow.devsper \
  --cluster localhost:7000 \
  --input repo_url=https://github.com/example/repo
```

---

## TUI with distributed runs

The TUI connects to any node's inspect socket:

```bash
# On the coordinator, expose the inspect socket
devsper run workflow.devsper \
  --cluster coordinator:7000 \
  --inspect-socket /tmp/devsper-run1.sock

# On the same machine, open the TUI
devsper tui run1
```

Or connect directly to the coordinator:

```bash
devsper inspect run1
```
