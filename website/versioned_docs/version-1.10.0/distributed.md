---
sidebar_position: 5
title: Distributed mode (v1.10)
---

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
   Or use the **Rust worker** for higher throughput: `HIVEMIND_WORKER_MODEL=github:gpt-4o`, `HIVEMIND_PYTHON_BIN=.venv/bin/python`, `HIVEMIND_RPC_PORT=0` (see `examples/distributed/README.md`).

3. **Run the controller** (submits a job):
   ```bash
   uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence."
   uv run python examples/distributed/run_controller.py "Your task" --parallel   # spread tasks across workers
   ```

Controller and workers use the same `run_id` (e.g. `"distributed-demo"` in the example configs). See `examples/distributed/README.md` in the repo for details and custom config paths.

## Config

**Controller** (`examples/distributed/controller.toml`): `[nodes] mode = "distributed"`, `role = "controller"`, `run_id = "distributed-demo"`, `[bus] backend = "redis"`.

**Worker** (`examples/distributed/worker.toml`): Same `run_id` and `[bus] backend = "redis"`, `role = "worker"`, `rpc_port = 7701`, `max_workers_per_node = 4`.

## Architecture

- **Controller** — Plans the task DAG, wins leader election, runs the dispatch loop, saves scheduler snapshots, tracks worker heartbeats and reclaims tasks from lost workers.
- **Workers** — Register, subscribe to TASK_READY, claim/execute tasks, publish TASK_COMPLETED/FAILED, send heartbeats (load, cached tools, completed task IDs for affinity).
- **Redis** — Message bus (pub/sub), cluster registry, leader lock, snapshot store.
- **Task routing** — Controller uses memory affinity, tool cache affinity, and load; workers with a different major.minor version are excluded.

## CLI: node commands

- **`hivemind node start [--role] [--port] [--workers] [--tags]`** — Start a node (config-driven).
- **`hivemind node status [--controller-url]`** — GET controller `/status`.
- **`hivemind node workers [--controller-url]`** — List workers.
- **`hivemind node drain <node_id>`** — Stop that worker from taking new tasks.
- **`hivemind node logs [--follow]`** — Stream events from controller.

## Doctor

When `[nodes] mode = "distributed"`, `hivemind doctor` checks Redis reachability, fastapi/uvicorn installation, and warns if `rpc_token` is not set. When mode is single, it reports "Running in single-node mode — no cluster checks needed."
