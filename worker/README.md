# hivemind-worker

Rust worker node for the hivemind distributed AI swarm runtime. Handles task claiming, execution orchestration, bus communication, heartbeating, and concurrency; agent/LLM/tool logic runs in Python via subprocess or PyO3.

## Docker

```bash
docker pull ghcr.io/rithulkamesh/hivemind-worker:latest
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HIVEMIND_NODE_ROLE` | `hybrid` | `controller` \| `worker` \| `hybrid` |
| `HIVEMIND_NODE_ID` | (uuid) | Node ID; auto-generated if unset |
| `HIVEMIND_NODE_TAGS` | (empty) | Comma-separated tags, e.g. `gpu,high-memory` |
| `HIVEMIND_MAX_WORKERS` | `4` | Max concurrent tasks per node |
| `HIVEMIND_RPC_PORT` | `7700` | HTTP port for /health, /status, /tasks, /control; use `0` for any free port (multiple workers on one host) |
| `HIVEMIND_RPC_TOKEN` | (none) | Optional auth for protected endpoints |
| `HIVEMIND_REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `HIVEMIND_RUN_ID` | (required) | Run ID for this cluster |
| `HIVEMIND_HEARTBEAT_INTERVAL` | `10` | Heartbeat interval (seconds) |
| `HIVEMIND_CLAIM_TIMEOUT` | `30` | Claim grant wait (seconds) |
| `HIVEMIND_LOG_LEVEL` | `info` | trace \| debug \| info \| warn \| error |
| `HIVEMIND_LOG_FORMAT` | `text` | text \| json (json in container) |
| `HIVEMIND_PYTHON_BIN` | `python3` | Python for subprocess executor |
| `HIVEMIND_WORKER_MODEL` | `mock` | Model for agent (e.g. `github:gpt-4o`); must match controller worker model for real LLM results |
| `HIVEMIND_EXECUTOR_MODE` | `subprocess` | subprocess \| pyo3 |

## Health check

HTTP GET `/health` returns node_id, role, healthy, uptime_seconds, version. Use for Docker/Kubernetes healthchecks.

## Build from source

```bash
cargo build --release
# Binary: target/release/hivemind-worker
```

With PyO3 executor (embedded Python):

```bash
cargo build --release --features pyo3-executor
```

## Supported platforms

- linux/amd64
- linux/arm64
