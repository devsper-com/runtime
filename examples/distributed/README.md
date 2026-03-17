# Distributed mode on one machine (v1.10)

Run a **controller** and one or more **workers** on a single computer using Redis. Good for testing v1.4–v1.10 (bus, checkpoint, distributed nodes, leader election, task routing).

**Provider:** Examples use the **GitHub provider** (Copilot API). Set `GITHUB_TOKEN` in the environment (or `devsper credentials set github token`). Config uses `planner = "github:gpt-4o"` and `worker = "github:gpt-4o"`.

**Workers:** Controllers are configured with `deregister_stale_workers = false`, so workers are never removed from the registry.

## Prerequisites

- Python 3.12+ with devsper and **distributed** extras (Redis, FastAPI, Uvicorn)
- Docker (for Redis)
- `GITHUB_TOKEN` (for real LLM calls; otherwise use `[models] planner = "mock"` / `worker = "mock"` in the TOML)

```bash
# From project root
uv sync --extra distributed
# or: pip install -e ".[distributed]"
```

## 1. Start Redis

From the **project root**:

```bash
docker compose up -d
docker compose ps   # optional: check Redis is up
```

## 2. Start one or more workers

In **separate terminals**, start workers (they register with Redis and wait for tasks):

```bash
# Terminal A — Python worker
uv run python examples/distributed/run_worker.py

# Terminal B (optional second worker)
uv run python examples/distributed/run_worker.py
```

Leave them running. You should see: `Worker running (run_id=distributed-demo). Ctrl+C to stop.`

**Rust worker (optional)** — From `runtime/`, build the binary, then run it via the same script (loads `.env` and `worker.toml`; uses current Python as `DEVSPER_PYTHON_BIN` for the agent subprocess):

```bash
cd runtime
cargo build --release -p devsper-worker
uv run python examples/distributed/run_worker.py --rust
```

For multiple workers on one machine, set `DEVSPER_RPC_PORT=0` in env. To run the binary directly with custom env:

```bash
DEVSPER_RUN_ID=distributed-demo DEVSPER_REDIS_URL=redis://localhost:6379 \
  DEVSPER_PYTHON_BIN=.venv/bin/python DEVSPER_RPC_PORT=0 \
  DEVSPER_WORKER_MODEL=github:gpt-4o ./worker/target/release/devsper-worker
```

## 3. Run the controller (submit a job)

In **another terminal**:

```bash
uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence."
```

The controller will plan subtasks, become leader, dispatch tasks to workers over Redis, and print results when done.

To run **all subtasks in parallel** (no dependency chain), use `--parallel`. Tasks are sent to **all available workers**; if you start only one worker, that worker gets all tasks. Start **2+ workers** in separate terminals to spread load:

```bash
uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence." --parallel
```

### Parallel survey (use case: independent tasks, no planner)

For a **proper parallel use case** with no planner and no dependency chain, use the survey script. It runs 5 independent questions at once (one per worker):

```bash
# Start workers first, then:
uv run python examples/distributed/parallel_survey.py
```

Uses the same GitHub provider and config; workers are never deregistered.

## Config files

- **`controller.toml`** – controller node: Redis URL, `nodes.mode=distributed`, `nodes.role=controller`, shared `run_id`
- **`worker.toml`** – worker node: same Redis URL and `run_id`, `nodes.role=worker`

Both use `run_id = "distributed-demo"` so they form one cluster. To use a custom run ID:

```bash
export DEVSPER_RUN_ID=my-run-1
# then start workers and controller (same value in both)
```

## Custom config paths

```bash
uv run python examples/distributed/run_controller.py "Your task" --config /path/to/controller.toml
uv run python examples/distributed/run_worker.py --config /path/to/worker.toml
```

## Features used in this example

| Version | Feature |
|--------|---------|
| v1.9   | Redis bus, scheduler snapshot, checkpoint |
| v1.10  | Controller node, worker node, cluster registry, leader election, shared state backend, task routing |

## Troubleshooting

- **"No workers in registry"** or **"Task … claim timed out, re-queuing"**  
  Start one or more workers *before* running the controller, and use the same `run_id` (e.g. `distributed-demo` in the example configs). The controller prints how many workers it sees and progress (e.g. `Progress: 1/5 completed, 4 pending`).
- **Tasks claim but never complete (controller says "claim timed out" after 2 min)**  
  The worker was stuck in the LLM call. Workers now have a **90s execution timeout** (`nodes.task_execution_timeout_seconds`): if the model doesn’t respond in time, the worker publishes TASK_FAILED and the controller marks the task failed so the run can finish. Ensure `GITHUB_TOKEN` is set and the model endpoint is responsive; increase the timeout in `worker.toml` if needed.
- **Rust worker: "empty response from agent"**  
  Set `DEVSPER_PYTHON_BIN` to the interpreter that has `devsper` installed (e.g. `.venv/bin/python`).
- **"(Error: Connection error.)" or TASK_COMPLETED empty result**  
  Workers call the LLM (Azure, GitHub, OpenAI, etc.) in their own process. If that process doesn’t have the provider’s credentials or can’t reach the API, you get a connection error and empty result. **Fix:** Run each worker in an environment where the right env vars are set (e.g. `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` for `azure:...`, or `GITHUB_TOKEN` for `github:...`). Export them in the same terminal before `uv run python examples/distributed/run_worker.py`, or use `devsper credentials set azure endpoint <url>` and `devsper credentials set azure api_key <key>` (then start the worker in the same user/session so keychain is available). The worker logs a warning at startup if it detects missing credentials for the configured model.
- **All results show (none)**  
  Rust workers default to `DEVSPER_WORKER_MODEL=mock`. Set `DEVSPER_WORKER_MODEL` to match the controller’s worker model (e.g. `DEVSPER_WORKER_MODEL=github:gpt-4o` when using the example config with `[models] worker = "github:gpt-4o"`) so the agent uses the real LLM and returns content. If you see `(Error: ...)` in results, fix that (e.g. missing `GITHUB_TOKEN` or keychain).
- **Only one worker gets tasks**  
  Without `--parallel`, the planner creates a dependency chain so the router sends dependent tasks to the same worker (for affinity). Use `--parallel` to run subtasks independently and spread load: `uv run python examples/distributed/run_controller.py "Your prompt" --parallel`.
- **Progress stuck at 2/5 (or similar)**  
  LLM calls often take 10–60s per task. Wait a bit; the other workers are likely still running. If a worker doesn’t claim within `task_claim_timeout_seconds` (default 120; example config uses 180), the controller re-queues the task so another worker can take it. Rust workers allow up to 300s per task execution by default.
- **Next run doesn’t use workers**  
  Each time you run the controller it’s a new run: new tasks, fresh dispatch. Workers that were free from the previous run will get tasks. If you see “Restored scheduler from snapshot” with the wrong task count, that was a bug (now fixed: snapshot is only restored when task IDs match).
- **More logs**
  Controller and worker show dispatch/claim/execute/complete at INFO. Use `export DEVSPER_LOG_LEVEL=DEBUG` for more detail.

## Stop

- Workers: Ctrl+C in each worker terminal.
- Redis: `docker compose down`
