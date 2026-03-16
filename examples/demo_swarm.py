#!/usr/bin/env python3
# ruff: noqa: E402
"""
Demo: run a research-style task with the swarm, show logs, print final result.

Usage:
    uv run python examples/demo_swarm.py
    uv run python examples/demo_swarm.py "Your task here"
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import devsper.tools  # noqa: F401
from devsper.utils.event_logger import EventLog
from devsper.swarm.swarm import Swarm
from devsper.memory.memory_router import MemoryRouter
from devsper.memory.memory_store import get_default_store
from devsper.memory.memory_index import MemoryIndex


def get_worker_model() -> str:
    if os.environ.get("DEVSPER_WORKER_MODEL"):
        return os.environ["DEVSPER_WORKER_MODEL"]
    if os.environ.get("GITHUB_TOKEN"):
        return "github:gpt-4o"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


def get_planner_model() -> str:
    if os.environ.get("DEVSPER_PLANNER_MODEL"):
        return os.environ["DEVSPER_PLANNER_MODEL"]
    return get_worker_model()


def main() -> None:
    task = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "What is swarm intelligence? Summarize in one short paragraph."
    )
    print("=== devsper Demo ===\n")
    print("Task:", task)
    print()

    event_log = EventLog()
    store = get_default_store()
    index = MemoryIndex(store)
    memory_router = MemoryRouter(store=store, index=index, top_k=5)

    swarm = Swarm(
        worker_count=2,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=memory_router,
        use_tools=False,
    )

    print("--- Running swarm ---\n")
    results = swarm.run(task)

    print("--- Event log (recent) ---\n")
    events = event_log.read_events()
    for ev in events[-20:]:
        payload = ev.payload or {}
        tid = payload.get("task_id", "")
        extra = f" {tid}" if tid else ""
        print(f"  {ev.type.value}{extra}")

    print("\n--- Final result ---\n")
    for task_id, result in results.items():
        print(f"[{task_id}]")
        print(result or "(no output)")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
