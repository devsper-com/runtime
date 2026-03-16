#!/usr/bin/env python3
"""
Run a distributed job: plan on this process, start controller, dispatch to workers over Redis.

Requires: Redis (docker compose up -d), one or more workers already running.
Usage:
  uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence"
  uv run python examples/distributed/run_controller.py "Hello" --parallel   # spread tasks across workers (no dependency chain)
  uv run python examples/distributed/run_controller.py "Hello" --config examples/distributed/controller.toml

Features exercised: v1.9 bus + checkpoint, v1.10 controller, registry, election, state backend.
Without --parallel, the planner creates a dependency chain so one worker tends to get all tasks (by design).
Use --parallel to run subtasks independently and spread load across multiple workers.
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

# Show controller/worker activity (dispatch, claim, progress)
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


async def main_async(task: str, config_path: str, parallel: bool = False) -> dict:
    _check_distributed_deps()
    from uuid import uuid4
    from devsper.config import get_config
    from devsper.types.task import Task
    from devsper.utils.event_logger import EventLog
    from devsper.swarm.planner import Planner
    from devsper.swarm.scheduler import Scheduler
    from devsper.intelligence.strategy_selector import StrategySelector
    from devsper.intelligence.strategies import get_strategy_for
    from devsper.bus.backends.redis import RedisBus
    from devsper.cluster.registry import ClusterRegistry
    from devsper.cluster.election import LeaderElector
    from devsper.cluster.state_backend import RedisStateBackend
    from devsper.cluster.router import TaskRouter
    from devsper.nodes.controller import ControllerNode

    cfg = get_config(config_path=config_path)
    run_id = getattr(getattr(cfg, "nodes", None), "run_id", None) or os.environ.get("DEVSPER_RUN_ID") or str(uuid4())
    events_dir = getattr(cfg, "events_dir", ".devsper/events")
    event_log = EventLog(events_folder_path=events_dir, run_id=run_id)

    # Plan
    root = Task(id="root", description=task, dependencies=[])
    selector = StrategySelector()
    selected = selector.select(root)
    strategy_instance = get_strategy_for(selected)
    planner = Planner(
        model_name=cfg.planner_model,
        event_log=event_log,
        strategy=strategy_instance,
        prompt_suffix=selector.suggest_planner_prompt_suffix(selected),
        knowledge_graph=None,
        guide_planning=False,
        min_confidence=0.30,
        parallel=parallel,
    )
    subtasks = planner.plan(root)

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

    # Brief delay so leader election and first dispatch can run
    await asyncio.sleep(1.0)
    workers = await registry.get_workers()
    if not workers:
        print("No workers in registry. Start workers first (run_worker.py), then run this script.", file=sys.stderr)
    else:
        print(f"Workers visible: {len(workers)} ({', '.join(w.node_id[:8] for w in workers)})", file=sys.stderr)
    total = len(scheduler.get_all_tasks())
    print(f"Run ID: {run_id}. Tasks: {total}. Waiting for workers to complete...", file=sys.stderr)
    if not parallel and len(workers) > 1:
        print("Tip: use --parallel to spread tasks across workers (no dependency chain).", file=sys.stderr)
    print("  (LLM calls can take 10–60s per task; workers run in parallel.)", file=sys.stderr)

    last_completed = -1
    while not scheduler.is_finished():
        await asyncio.sleep(0.5)
        completed = sum(1 for t in scheduler.get_all_tasks() if t.status.value == 2)
        pending = sum(1 for t in scheduler.get_all_tasks() if t.status.value == 0)
        if completed != last_completed:
            print(f"  Progress: {completed}/{total} completed, {pending} pending", file=sys.stderr)
            last_completed = completed
    results = scheduler.get_results()
    await bus.stop()
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Run distributed controller (plan + dispatch)")
    ap.add_argument("task", nargs="?", default="Summarize swarm intelligence in one sentence.", help="Task prompt")
    ap.add_argument("--config", "-c", default=str(ROOT / "examples" / "distributed" / "controller.toml"), help="Controller TOML")
    ap.add_argument("--parallel", "-p", action="store_true", help="Run all subtasks in parallel (no dependency chain)")
    args = ap.parse_args()
    results = asyncio.run(main_async(args.task, args.config, parallel=args.parallel))
    print("--- Results ---")
    for tid, text in results.items():
        print(f"[{tid}]\n{text or '(none)'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
