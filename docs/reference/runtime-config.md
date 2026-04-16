# Runtime Configuration

All runtime settings are controlled via environment variables or CLI flags. There is no required config file.

---

## Workers

| Variable          | CLI flag        | Default | Description                         |
|-------------------|-----------------|---------|-------------------------------------|
| `DEVSPER_WORKERS` | `--workers N`   | `4`     | Max concurrent tasks (semaphore).   |

```bash
devsper run workflow.devsper --workers 8
DEVSPER_WORKERS=8 devsper run workflow.devsper
```

---

## Message Bus

| Variable       | Values                  | Default    |
|----------------|-------------------------|------------|
| `DEVSPER_BUS`  | `memory`, `redis`, `kafka` | `memory` |

### Memory bus (default)

No external deps. Single-process only. Uses tokio broadcast channels.

```bash
DEVSPER_BUS=memory devsper run workflow.devsper
```

### Redis bus

```bash
DEVSPER_BUS=redis
REDIS_URL=redis://localhost:6379
```

Enables multi-node event streaming. Required for distributed cluster mode.

### Kafka bus

```bash
DEVSPER_BUS=kafka
KAFKA_BROKERS=localhost:9092
KAFKA_TOPIC=devsper-events      # default: "devsper-events"
```

At-least-once delivery with consumer groups. Use for durable event log across restarts.

---

## Graph evolution

| Variable                  | Default | Description                                     |
|---------------------------|---------|------------------------------------------------|
| `DEVSPER_ALLOW_MUTATIONS` | `true`  | Whether agents may submit graph mutations.      |
| `DEVSPER_MAX_DEPTH`       | `10`    | Max mutation nesting depth.                     |
| `DEVSPER_SPECULATIVE`     | `false` | Enable speculative node pre-execution.          |
| `DEVSPER_MAX_MUTATIONS`   | `1000`  | Hard cap on total mutations per run.            |

---

## Memory backend

| Variable                  | Values                       | Default  |
|---------------------------|------------------------------|----------|
| `DEVSPER_MEMORY_BACKEND`  | `local`, `sqlite`, `postgres`| `local`  |
| `DATABASE_URL`            | Postgres connection string   | —        |

```bash
DEVSPER_MEMORY_BACKEND=postgres \
DATABASE_URL=postgres://user:pass@localhost/devsper \
devsper run workflow.devsper
```

`local` uses an in-process HashMap (lost on exit).  
`sqlite` persists to `~/.local/share/devsper/memory.db`.  
`postgres` uses pgvector for semantic search.

---

## Inspect socket

The `--inspect-socket` flag (or env var) exposes a Unix domain socket with a JSON-RPC stream of live graph events. The TUI connects to this socket.

```bash
devsper run workflow.devsper --inspect-socket /tmp/devsper-run1.sock

# In another terminal
devsper tui run1
```

| Variable                   | CLI flag                    | Default  |
|----------------------------|-----------------------------|----------|
| `DEVSPER_INSPECT_SOCKET`   | `--inspect-socket <path>`   | disabled |

The socket path follows the pattern `/tmp/devsper-{run-id}.sock` when the TUI initiates the connection.

---

## Logging

devsper uses the `tracing` crate. Control log levels via `RUST_LOG`:

```bash
RUST_LOG=devsper=info devsper run workflow.devsper
RUST_LOG=devsper_graph=debug,devsper_executor=info devsper run workflow.devsper
RUST_LOG=trace devsper run workflow.devsper   # very verbose
```

Log format defaults to human-readable. For structured JSON:

```bash
DEVSPER_LOG_FORMAT=json devsper run workflow.devsper
```

---

## Cluster

See [Distributed Setup](../guides/distributed-setup.md) for cluster-specific configuration.

| Variable               | CLI flag           | Description                        |
|------------------------|--------------------|------------------------------------|
| `DEVSPER_CLUSTER`      | `--cluster <addr>` | Coordinator address for run submit.|
| `DEVSPER_LISTEN`       | `--listen <addr>`  | Bind address for peer node.        |
| `DEVSPER_JOIN`         | `--join <addr>`    | Coordinator to join on startup.    |
