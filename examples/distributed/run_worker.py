#!/usr/bin/env python3
"""
Start a worker node: connect to Redis, register, wait for TASK_READY and execute.

Requires: Redis (docker compose up -d). Start one or more workers before run_controller.py.
Usage:
  uv run python examples/distributed/run_worker.py
  uv run python examples/distributed/run_worker.py --config examples/distributed/worker.toml

Features: v1.9 bus, v1.10 worker, registry, task claim, agent execution.
"""

import argparse
import asyncio
import logging
import os
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
        print("Redis required. Install: pip install 'hivemind-ai[distributed]'", file=sys.stderr)
        sys.exit(1)


async def run_worker_forever(config_path: str) -> None:
    _check_distributed_deps()
    from hivemind.config import get_config
    from hivemind.utils.event_logger import EventLog
    from hivemind.bus.backends.redis import RedisBus
    from hivemind.cluster.registry import ClusterRegistry
    from hivemind.nodes.worker import WorkerNode
    from hivemind.agents.agent import Agent
    from hivemind.reasoning.store import ReasoningStore
    from hivemind.memory.memory_router import MemoryRouter
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex

    cfg = get_config(config_path=config_path)
    run_id = (
        getattr(getattr(cfg, "nodes", None), "run_id", None)
        or os.environ.get("HIVEMIND_RUN_ID")
        or "distributed-demo"
    )
    events_dir = getattr(cfg, "events_dir", ".hivemind/events")
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
        from hivemind.tools.selector import get_tools_for_task
        tool_selector = lambda desc, role=None, score_store=None: get_tools_for_task(
            desc or "", role=role, score_store=score_store
        )
    except Exception:
        tool_selector = lambda desc, role=None, score_store=None: []
    try:
        from hivemind.tools.scoring import get_default_score_store
        score_store = get_default_score_store()
    except Exception:
        score_store = None
    try:
        from hivemind.swarm.prefetcher import TaskPrefetcher
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Start distributed worker")
    ap.add_argument("--config", "-c", default=str(ROOT / "examples" / "distributed" / "worker.toml"), help="Worker TOML")
    args = ap.parse_args()
    try:
        asyncio.run(run_worker_forever(args.config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
