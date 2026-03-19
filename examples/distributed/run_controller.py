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

# --- ROOT CAUSE DIAGNOSIS (from code; 2026-03-17) ---
# Q1 — Channel mismatch?
#   - Rust worker publishes completion with topic "task.completed" (worker/src/types/event.rs),
#     and RedisBus maps to channel f"{topic}:{run_id}" (worker/src/bus.rs) => "task.completed:{run_id}".
#   - Python controller subscribes to TASK_COMPLETED == "task.completed" (devsper/bus/topics.py),
#     and RedisBus maps to channel f"{topic}:{run_id}" (devsper/bus/backends/redis.py) => "task.completed:{run_id}".
#   - The strings match. No channel-name mismatch.
#   - Note: there is no devsper/bus/redis_bus.py in this repo; the backend lives at devsper/bus/backends/redis.py.
#
# Q2 — Result delivery to TUI?
#   - When controller receives TASK_COMPLETED, it runs ControllerNode._on_task_completed()
#     which calls run_view.on_task_status_changed(task_id, "completed", sender_id) (devsper/nodes/controller.py).
#
# Q3 — Run termination?
#   - Controller (and this example script) consider the run complete when Scheduler.is_finished() becomes True.
#     If controller never sees completions (e.g. wrong run_id scope), the run waits indefinitely / gets cancelled.
#
# Q4 — TUI refresh loop?
#   - DistributedRunView has a timer-based refresh loop calling live.update(...) every poll_interval
#     (devsper/cli/ui/run_view.py: DistributedRunView._refresh_loop).
# --- END DIAGNOSIS ---

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

# Keep terminal/TUI readable by default. Opt in to INFO with DEVSPER_LOG_LEVEL=INFO.
_log_level_name = os.environ.get("DEVSPER_LOG_LEVEL", "WARNING").strip().upper()
_log_level = getattr(logging, _log_level_name, logging.WARNING)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def _check_distributed_deps() -> None:
    try:
        import redis.asyncio  # noqa: F401
    except ImportError:
        from devsper.cli.ui.theme import console
        console.print("[hive.error]Redis required.[/] Install: `pip install 'devsper[distributed]'`")
        sys.exit(1)


async def main_async(task: str, config_path: str, parallel: bool = False) -> dict:
    _check_distributed_deps()
    # Load .env from project root (runtime/) so API keys are available for planner
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    from uuid import uuid4
    from devsper.config import get_config
    # Register built-in tools in this controller process (import side effects).
    # This is required for controller-executed tool calls from Rust workers.
    try:
        import devsper.tools  # noqa: F401
    except Exception:
        pass
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
    from devsper.cli.ui.theme import console

    cfg = get_config(config_path=config_path)
    # IMPORTANT: workers scope bus/registry channels by run_id. If controller picks a random uuid by default
    # but workers default to "distributed-demo", controller will never see workers/results.
    run_id = (
        getattr(getattr(cfg, "nodes", None), "run_id", None)
        or os.environ.get("DEVSPER_RUN_ID")
        or "distributed-demo"
    )
    events_dir = getattr(cfg, "events_dir", ".devsper/events")
    event_log = EventLog(events_folder_path=events_dir, run_id=run_id)
    log_path = getattr(event_log, "log_path", None)

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
    # Use controller.scheduler every time: it is replaced by restore() in _become_leader, so the
    # script must not cache it or the run would never finish (old scheduler never gets completions).
    total = len(controller.scheduler.get_all_tasks())
    # No bare prints here when TUI is active; in headless we print progress.
    if os.environ.get("DEVSPER_HEADLESS", "0").strip().lower() in ("1", "true", "yes") or os.environ.get("DEVSPER_CONTROLLER_TUI", "1").strip() == "0":
        if not workers:
            console.print("[hive.warning]No workers in registry.[/] Start workers first (`run_worker.py`), then rerun.")
        else:
            console.print(
                f"[hive.muted]Workers visible:[/] {len(workers)} ({', '.join(w.node_id[:8] for w in workers)})"
            )
            if parallel and len(workers) == 1:
                console.print("[hive.muted]Tip:[/] with `--parallel`, start 2+ workers to spread tasks.")
        console.print(f"[hive.muted]Run ID:[/] {run_id[:8]}  ·  Tasks: {total}  ·  waiting for completion…")
        if not parallel and len(workers) > 1:
            console.print("[hive.muted]Tip:[/] use `--parallel` to spread tasks across workers.")

    while not controller.scheduler.is_finished():
        await asyncio.sleep(0.5)
    results = controller.scheduler.get_results()
    await bus.stop()

    # Final summary printed after Live has stopped (or if TUI disabled).
    try:
        from devsper.cli.ui.run_view import RunViewState, print_run_summary
        state = RunViewState(
            run_id=run_id,
            run_id_short=(run_id or "")[:8],
            planner_message="",
            planner_visible=False,
            worker_count=len(workers),
        )
        state.update_from_events(log_path)
        print_run_summary(state, results, summary_only=False)
    except Exception:
        pass
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Run distributed controller (plan + dispatch)")
    ap.add_argument("task", nargs="?", default="Summarize swarm intelligence in one sentence.", help="Task prompt")
    ap.add_argument("--config", "-c", default=str(ROOT / "examples" / "distributed" / "controller.toml"), help="Controller TOML")
    ap.add_argument("--parallel", "-p", action="store_true", help="Run all subtasks in parallel (no dependency chain)")
    ap.add_argument("--headless", action="store_true", help="No TUI; HITL clarifications auto-resolve with defaults (set DEVSPER_HEADLESS=1)")
    args = ap.parse_args()
    if args.headless:
        os.environ["DEVSPER_HEADLESS"] = "1"
    results = asyncio.run(main_async(args.task, args.config, parallel=args.parallel))
    return 0


if __name__ == "__main__":
    sys.exit(main())
