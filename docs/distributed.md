# Distributed mode (v1.10)

Run a **controller** and one or more **workers** across processes or machines. The controller plans tasks and dispatches them over Redis; workers execute tasks and report results. Single-node mode (default) runs controller + worker in one process with no Redis.

## When to use

- **Single-node (default)** — One process, no Redis. Use for local development and simple runs. Set `[nodes] mode = "single"` or omit; behavior matches pre-v1.10.
- **Distributed** — Multiple worker processes or machines, Redis for bus and cluster state. Use for scaling or dedicated controller/worker roles. Set `[nodes] mode = "distributed"`, `role = "controller"` or `"worker"`, and `[bus] backend = "redis"`.

## Prerequisites for distributed

1. **Redis** — Run Redis (e.g. `docker compose up -d` using the project `docker-compose.yml`).
2. **Optional dependency group** — Install Redis and RPC deps:
   ```bash
   pip install 'hivemind-ai[distributed]'
   # or: uv sync --extra distributed
   ```

## Quick start: one machine

1. **Start Redis** (from project root):
   ```bash
   docker compose up -d
   ```

2. **Start one or more workers** (separate terminals):
   ```bash
   uv run python examples/distributed/run_worker.py
   ```

3. **Run the controller** (submits a job):
   ```bash
   uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence."
   ```

Controller and workers use the same `run_id` (e.g. `"distributed-demo"` in the example configs) so they form one cluster. See [examples/distributed/README.md](../examples/distributed/README.md) for details and custom config paths.

## Config

**Controller** (`examples/distributed/controller.toml`):

```toml
[nodes]
mode = "distributed"
role = "controller"
run_id = "distributed-demo"
rpc_port = 7700

[bus]
backend = "redis"
redis_url = "redis://localhost:6379"
```

**Worker** (`examples/distributed/worker.toml`):

```toml
[nodes]
mode = "distributed"
role = "worker"
run_id = "distributed-demo"
rpc_port = 7701
max_workers_per_node = 4

[bus]
backend = "redis"
redis_url = "redis://localhost:6379"
```

Same `run_id` and `redis_url` on both. For multiple workers, use the same worker config (optionally different `rpc_port` and `node_tags`).

## Architecture

```
  Controller (Python)  <--->  Redis (pub/sub, registry, leader, snapshot)  <--->  Worker 1 (Rust or Python)
                                                                           <--->  Worker 2 (Rust or Python)
                                                                           <--->  Worker N ...
```

- **Controller** — Plans the task DAG, wins leader election, runs the dispatch loop, saves scheduler snapshots to the state backend, tracks worker heartbeats and reclaims tasks from lost workers.
- **Workers** — Register with the cluster, subscribe to TASK_READY, claim tasks (one claim granted per task), execute via the agent, publish TASK_COMPLETED/FAILED, send heartbeats (load, cached tools, completed task IDs for affinity). Can run as **Python** (`run_worker.py`) or **Rust** (`hivemind-worker` binary / Docker image).
- **Redis** — Message bus (pub/sub), cluster registry (`hivemind:cluster:{run_id}:nodes`), leader lock (`hivemind:leader:{run_id}`), snapshot store (`hivemind:snapshot:{run_id}`).
- **Task routing** — Controller uses `TaskRouter` to pick a worker by memory affinity, tool cache affinity, and load; workers with a different major.minor version are excluded.

## Rust worker (hivemind-worker)

For higher throughput and lower memory use, run workers as the Rust binary or Docker image.

**Quick start with Docker:**

```bash
# Redis
docker compose up -d

# Worker (Rust image; replace rithulkamesh with your GitHub org or username)
docker run -e HIVEMIND_RUN_ID=distributed-demo -e HIVEMIND_REDIS_URL=redis://host.docker.internal:6379 -p 7700:7700 ghcr.io/rithulkamesh/hivemind-worker:latest
```

**Docker Compose example** (controller + 3 Rust workers + Redis):

```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, timeout: 3s }
  controller:
    build: .
    command: ["uv", "run", "python", "examples/distributed/run_controller.py", "Your task here."]
    environment:
      HIVEMIND_RUN_ID: distributed-demo
      HIVEMIND_REDIS_URL: redis://redis:6379
    depends_on: { redis: { condition: service_healthy } }
  worker:
    image: ghcr.io/rithulkamesh/hivemind-worker:latest
    environment:
      HIVEMIND_RUN_ID: distributed-demo
      HIVEMIND_REDIS_URL: redis://redis:6379
      HIVEMIND_RPC_PORT: 7700
    depends_on: { redis: { condition: service_healthy } }
    deploy: { replicas: 3 }
```

**Configuration (environment)** — Rust worker reads 12-factor env vars; see `worker/README.md` for the full list. Key ones: `HIVEMIND_RUN_ID`, `HIVEMIND_REDIS_URL`, `HIVEMIND_RPC_PORT` (use `0` for any free port when running multiple workers on one host), `HIVEMIND_WORKER_MODEL` (default `mock`; set to `github:gpt-4o` etc. for real LLM results), `HIVEMIND_MAX_WORKERS`, `HIVEMIND_PYTHON_BIN` (venv Python so subprocess loads hivemind), `HIVEMIND_EXECUTOR_MODE` (subprocess | pyo3). Credentials (e.g. `GITHUB_TOKEN`) are injected from the keychain into the subprocess automatically.

**Executor modes** — **subprocess** (default): spawns `python -m hivemind.agents.run_agent` per task; no Python version coupling. **pyo3**: embeds Python via PyO3 for lower latency; build with `--features pyo3-executor`.

**Upgrading from Python worker (v1.9)** — Replace `uv run python examples/distributed/run_worker.py` with `hivemind-worker` (or the Docker image). Use the same `run_id` and `redis_url` as the controller. No change to controller or bus protocol.

## CLI: node commands

- **`hivemind node start [--role controller|worker|hybrid] [--port N] [--workers N] [--tags tag1,tag2]`** — Start a node (config-driven; set `nodes.mode` and `nodes.role` in TOML).
- **`hivemind node status [--controller-url URL]`** — GET controller `/status`; shows run, leader, task counts, workers.
- **`hivemind node workers [--controller-url URL]`** — List workers from controller status.
- **`hivemind node drain <node_id>`** — POST `/control` with `command: drain` to stop that worker from taking new tasks.
- **`hivemind node logs [--follow]`** — Stream events from controller (SSE).

## Doctor

When `[nodes] mode = "distributed"`, `hivemind doctor` checks Redis reachability, fastapi/uvicorn installation, and warns if `rpc_token` is not set. When mode is single, it reports "Running in single-node mode — no cluster checks needed."
