---
title: Distributed Mode
---

# Distributed Mode

Run a **controller** and one or more **workers** across processes or machines. The controller plans tasks and dispatches them over Redis; workers execute tasks and report results. Single-node mode (default) runs controller + worker in one process with no Redis.

## When to use

- **Single-node (default)** — One process, no Redis. Use for local development and simple runs.
- **Distributed** — Multiple worker processes or machines, Redis for bus and cluster state.

## Prerequisites

1. **Redis** — Run Redis (e.g. `docker compose up -d`).
2. **Optional dependency group:**
   ```bash
   pip install 'hivemind-ai[distributed]'
   ```

## Quick start

1. **Start Redis:**
   ```bash
   docker compose up -d
   ```

2. **Start workers** (separate terminals):
   ```bash
   uv run python examples/distributed/run_worker.py
   ```

3. **Run the controller:**
   ```bash
   uv run python examples/distributed/run_controller.py "Your task"
   ```

## Architecture

- **Controller** — Plans the task DAG, runs dispatch loop, tracks worker heartbeats.
- **Workers** — Register, claim/execute tasks, publish results, send heartbeats.
- **Redis** — Message bus (pub/sub), cluster registry, leader lock, snapshot store.
