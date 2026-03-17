#!/usr/bin/env python3
"""
Start a worker node: connect to Redis, register, wait for TASK_READY and execute.

Requires: Redis (docker compose up -d). Start one or more workers before run_controller.py.

Usage:
  uv run python examples/distributed/run_worker.py              # Python worker
  uv run python examples/distributed/run_worker.py --rust       # Rust worker (binary must be built)
  uv run python examples/distributed/run_worker.py --config examples/distributed/worker.toml

Python worker: full implementation in this script. Rust worker: spawns worker/target/release/devsper-worker
after loading .env and config so DEVSPER_RUN_ID, DEVSPER_REDIS_URL, DEVSPER_WORKER_MODEL, etc. are set.
"""

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Worker activity logs (task received, claim, execute, complete)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)


def _check_distributed_deps() -> None:
    try:
        import redis.asyncio  # noqa: F401
    except ImportError:
        print("Redis required. Install: pip install 'devsper[distributed]'", file=sys.stderr)
        sys.exit(1)


async def run_worker_forever(config_path: str) -> None:
    _check_distributed_deps()
    # Load .env from project root (runtime/) so AZURE_OPENAI_*, GITHUB_TOKEN, etc. are available
    _log = logging.getLogger(__name__)
    env_path = ROOT / ".env"
    env_loaded = False
    try:
        from dotenv import load_dotenv
        env_loaded = load_dotenv(env_path)
    except Exception as e:
        _log.debug("Could not load .env from %s: %s", env_path, e)
    from devsper.config import get_config
    from devsper.utils.event_logger import EventLog
    from devsper.bus.backends.redis import RedisBus
    from devsper.cluster.registry import ClusterRegistry
    from devsper.nodes.worker import WorkerNode
    from devsper.agents.agent import Agent
    from devsper.reasoning.store import ReasoningStore
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex

    cfg = get_config(config_path=config_path)
    worker_model = getattr(getattr(cfg, "models", None), "worker", None) or ""
    prefix = worker_model.split(":")[0].lower() if (worker_model and ":" in worker_model) else ""
    # Bare model names (e.g. gpt-5-mini) are resolved to Azure by config when AZURE_OPENAI_* is set
    if not prefix and worker_model and ("gpt-" in worker_model.lower() or "o1-" in worker_model.lower()):
        prefix = "azure"
    # Log credential status so "Connection error" can be diagnosed (check worker terminal, not controller)
    ep = key = tok = False
    if prefix == "azure":
        ep = bool(os.environ.get("AZURE_OPENAI_ENDPOINT"))
        key = bool(os.environ.get("AZURE_OPENAI_API_KEY"))
        _log.info(
            "Worker credentials: .env loaded=%s, AZURE_OPENAI_ENDPOINT set=%s, AZURE_OPENAI_API_KEY set=%s",
            env_loaded, ep, key,
        )
        if not ep or not key:
            _log.warning(
                "Worker model is %s but AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY is unset. "
                "Put them in runtime/.env or run: devsper credentials set azure endpoint <url> ; devsper credentials set azure api_key <key>",
                worker_model,
            )
    elif prefix == "github":
        tok = bool(os.environ.get("GITHUB_TOKEN"))
        _log.info("Worker credentials: .env loaded=%s, GITHUB_TOKEN set=%s", env_loaded, tok)
        if not tok:
            _log.warning("Worker model is %s but GITHUB_TOKEN is unset. Put it in runtime/.env or use devsper credentials set github token", worker_model)
    elif prefix == "openai":
        key = bool(os.environ.get("OPENAI_API_KEY"))
        _log.info("Worker credentials: .env loaded=%s, OPENAI_API_KEY set=%s", env_loaded, key)
        if not key:
            _log.warning("Worker model is %s but OPENAI_API_KEY is unset.", worker_model)
    else:
        _log.info("Worker credentials: .env loaded=%s, model=%s (no provider env check)", env_loaded, worker_model or "mock")
    # Print credential status to stderr so it's visible before any task logs
    if prefix == "azure":
        print(
            f"Worker credentials: .env loaded={env_loaded}, AZURE_OPENAI_ENDPOINT set={ep}, AZURE_OPENAI_API_KEY set={key}",
            file=sys.stderr,
        )
    elif prefix == "github":
        print(f"Worker credentials: .env loaded={env_loaded}, GITHUB_TOKEN set={tok}", file=sys.stderr)
    elif prefix == "openai":
        print(f"Worker credentials: .env loaded={env_loaded}, OPENAI_API_KEY set={key}", file=sys.stderr)
    run_id = (
        getattr(getattr(cfg, "nodes", None), "run_id", None)
        or os.environ.get("DEVSPER_RUN_ID")
        or "distributed-demo"
    )
    events_dir = getattr(cfg, "events_dir", ".devsper/events")
    event_log = EventLog(events_folder_path=events_dir, run_id=run_id)

    redis_url = getattr(getattr(cfg, "bus", None), "redis_url", "redis://localhost:6379")
    bus = RedisBus(redis_url=redis_url)
    await bus.start()
    redis_client = bus.redis_client
    registry = ClusterRegistry(redis_client, run_id)

    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    try:
        from devsper.tools.selector import get_tools_for_task
        tool_selector = lambda desc, role=None, score_store=None: get_tools_for_task(
            desc or "", role=role, score_store=score_store
        )
    except Exception:
        tool_selector = lambda desc, role=None, score_store=None: []
    try:
        from devsper.tools.scoring import get_default_score_store
        score_store = get_default_score_store()
    except Exception:
        score_store = None
    try:
        from devsper.swarm.prefetcher import TaskPrefetcher
        prefetcher = TaskPrefetcher(
            memory_router=memory_router,
            tool_selector=tool_selector,
            score_store=score_store,
            max_age_seconds=30.0,
        )
    except Exception:
        prefetcher = None

    def agent_factory(c):
        return Agent(
            model_name=getattr(c.models, "worker", "mock"),
            event_log=event_log,
            memory_router=memory_router,
            store_result_to_memory=False,
            use_tools=True,
            reasoning_store=ReasoningStore(),
            user_task="",
            parallel_tools=True,
            message_bus=None,
        )

    worker = WorkerNode(
        config=cfg,
        bus=bus,
        registry=registry,
        memory_router=memory_router,
        tool_selector=tool_selector,
        score_store=score_store,
        prefetcher=prefetcher,
        agent_factory=agent_factory,
        event_log=event_log,
        run_id=run_id,
        user_task="",
        message_bus=None,
    )
    await worker.start()
    print(f"Worker running (run_id={run_id}). Ctrl+C to stop.", file=sys.stderr)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await registry.deregister(worker.node_id)
            print("Worker deregistered.", file=sys.stderr)
        except Exception as e:
            print(f"Worker deregister failed: {e}", file=sys.stderr)
        await bus.stop()


def _run_rust_worker(config_path: str) -> int:
    """Load .env and config, then exec the Rust devsper-worker binary."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    from devsper.config import get_config
    cfg = get_config(config_path=config_path)
    nodes = getattr(cfg, "nodes", None)
    bus = getattr(cfg, "bus", None)
    models = getattr(cfg, "models", None)
    run_id = getattr(nodes, "run_id", None) or os.environ.get("DEVSPER_RUN_ID") or "distributed-demo"
    redis_url = getattr(bus, "redis_url", None) or os.environ.get("DEVSPER_REDIS_URL") or "redis://localhost:6379"
    worker_model = getattr(models, "worker", None) or os.environ.get("DEVSPER_WORKER_MODEL") or "mock"
    env = os.environ.copy()
    env["DEVSPER_RUN_ID"] = run_id
    env["DEVSPER_REDIS_URL"] = redis_url
    env["DEVSPER_WORKER_MODEL"] = worker_model
    env["DEVSPER_PYTHON_BIN"] = sys.executable  # so Rust worker's agent subprocess uses same venv
    # Use port 0 so each Rust worker gets a free port (multiple workers on one machine)
    env["DEVSPER_RPC_PORT"] = "0"
    # Look for binary: workspace target (cargo from runtime/), then worker target (cargo from runtime/worker/), then PATH
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [
        ROOT / "target" / "release" / f"devsper-worker{suffix}",       # workspace: cargo build from runtime/
        ROOT / "worker" / "target" / "release" / f"devsper-worker{suffix}",
    ]
    binary = None
    for p in candidates:
        if p.is_file():
            binary = p
            break
    if binary is None:
        in_path = shutil.which("devsper-worker")
        if in_path:
            binary = Path(in_path)
    if binary is None:
        print(
            "Rust worker binary not found. From runtime/ run: cargo build --release -p devsper-worker",
            file=sys.stderr,
        )
        print(f"  Then run: uv run python examples/distributed/run_worker.py --rust", file=sys.stderr)
        return 1
    print(f"Starting Rust worker: {binary} (run_id={run_id})", file=sys.stderr)
    return subprocess.run([str(binary)], env=env, cwd=str(ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Start distributed worker (Python or Rust)")
    ap.add_argument("--config", "-c", default=str(ROOT / "examples" / "distributed" / "worker.toml"), help="Worker TOML")
    ap.add_argument("--rust", action="store_true", help="Run the Rust worker binary instead of the Python worker")
    args = ap.parse_args()
    if args.rust:
        return _run_rust_worker(args.config)
    try:
        asyncio.run(run_worker_forever(args.config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
