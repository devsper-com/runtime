#!/usr/bin/env python3
"""
Parallel survey: run a fixed set of independent tasks in parallel (no planner).

Use case: multiple questions answered concurrently by different workers.
Uses GitHub provider (GITHUB_TOKEN). Workers are never deregistered (deregister_stale_workers = false).

Requires: Redis (docker compose up -d), one or more workers (run_worker.py), then:
  uv run python examples/distributed/parallel_survey.py
  uv run python examples/distributed/parallel_survey.py --config examples/distributed/controller.toml
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)


def _check_deps() -> None:
    try:
        import redis.asyncio  # noqa: F401
    except ImportError:
        print("Redis required. Install: pip install 'devsper[distributed]'", file=sys.stderr)
        sys.exit(1)


def _default_questions() -> list[tuple[str, str]]:
    """Return (task_id, description) for 5 independent parallel tasks."""
    return [
        ("q1", "In one sentence, what is swarm intelligence?"),
        ("q2", "In one sentence, what is emergent behavior?"),
        ("q3", "In one sentence, what is collective decision-making?"),
        ("q4", "In one sentence, what is stigmergy?"),
        ("q5", "In one sentence, what is a multi-agent system?"),
    ]


async def main_async(config_path: str) -> dict:
    _check_deps()
    from uuid import uuid4
    from devsper.config import get_config
    from devsper.types.task import Task, TaskStatus
    from devsper.utils.event_logger import EventLog
    from devsper.swarm.scheduler import Scheduler
    from devsper.bus.backends.redis import RedisBus
    from devsper.cluster.registry import ClusterRegistry
    from devsper.cluster.election import LeaderElector
    from devsper.cluster.state_backend import RedisStateBackend
    from devsper.cluster.router import TaskRouter
    from devsper.nodes.controller import ControllerNode

    cfg = get_config(config_path=config_path)
    run_id = getattr(getattr(cfg, "nodes", None), "run_id", None) or os.environ.get("DEVSPER_RUN_ID") or "parallel-survey"
    events_dir = getattr(cfg, "events_dir", ".devsper/events")
    event_log = EventLog(events_folder_path=events_dir, run_id=run_id)

    # Fixed parallel tasks: all independent (no dependencies) — all ready at once
    questions = _default_questions()
    subtasks = [Task(id=tid, description=desc, dependencies=[]) for tid, desc in questions]

    scheduler = Scheduler()
    scheduler.add_tasks(subtasks)
    scheduler.run_id = run_id

    redis_url = getattr(getattr(cfg, "bus", None), "redis_url", "redis://localhost:6379")
    bus = RedisBus(redis_url=redis_url)
    await bus.start()
    redis_client = bus.redis_client

    state_backend = RedisStateBackend(redis_client)
    registry = ClusterRegistry(redis_client, run_id)
    elector = LeaderElector(redis_client, run_id)
    try:
        import devsper
        version = getattr(devsper, "__version__", "1.10.0")
    except Exception:
        version = "1.10.0"
    router = TaskRouter(controller_version=version)

    controller = ControllerNode(
        config=cfg,
        scheduler=scheduler,
        bus=bus,
        state_backend=state_backend,
        registry=registry,
        elector=elector,
        router=router,
        event_log=event_log,
    )
    await controller.start()

    await asyncio.sleep(1.0)
    workers = await registry.get_workers()
    if not workers:
        print("No workers in registry. Start workers first (run_worker.py).", file=sys.stderr)
    else:
        print(f"Workers: {len(workers)}. Tasks: {len(subtasks)} (all ready in parallel).", file=sys.stderr)
    # Use controller.scheduler every time: it gets replaced by restored snapshot when leader is elected
    last_completed = -1
    while not controller.scheduler.is_finished():
        await asyncio.sleep(0.5)
        sched = controller.scheduler
        total = len(sched.get_all_tasks())
        completed = sum(1 for t in sched.get_all_tasks() if t.status.value == 2)
        if completed != last_completed:
            print(f"  Progress: {completed}/{total} completed", file=sys.stderr)
            last_completed = completed
    # Include failed tasks with their error (get_results() only returns completed)
    sched = controller.scheduler
    results = {}
    for t in sched.get_all_tasks():
        if t.status == TaskStatus.COMPLETED:
            results[t.id] = t.result or ""
        elif t.status == TaskStatus.FAILED:
            results[t.id] = f"(failed: {t.error or 'unknown'})"
        else:
            results[t.id] = "(no result)"
    await bus.stop()
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Run parallel survey (independent tasks, GitHub provider)")
    ap.add_argument("--config", "-c", default=str(ROOT / "examples" / "distributed" / "controller.toml"), help="Controller TOML")
    args = ap.parse_args()
    results = asyncio.run(main_async(args.config))
    print("--- Results ---")
    for tid, text in results.items():
        print(f"[{tid}]\n{text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
