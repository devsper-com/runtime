#!/usr/bin/env python3
"""
Refactor Candidate Finder: repo path → large functions, refactor candidates, complexity → refactor suggestions.

Workflow: large_function_detector → refactor_candidate_detector → complexity analysis (via tools)
→ swarm to prioritize and summarize. Uses tools, memory, swarm runtime.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import (
    build_report_from_swarm,
    get_memory_router,
    log,
    run_tool_safe,
    save_json,
    save_markdown,
    store_in_memory,
)
from examples._config import get_planner_model, get_worker_model

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Find refactor candidates in a repository")
    parser.add_argument("path", nargs="?", default=".", help="Repository root path")
    args = parser.parse_args()
    repo = Path(args.path).resolve()
    if not repo.exists() or not repo.is_dir():
        log(f"Error: path not found: {repo}")
        sys.exit(1)

    log("Refactor Candidate Finder")
    log("Step 1: Large function detector")
    large_out = run_tool_safe("large_function_detector", {"path": str(repo)})
    log("Step 2: Refactor candidate detector")
    refactor_out = run_tool_safe("refactor_candidate_detector", {"path": str(repo)})

    store_in_memory(large_out[:6000], "semantic", tags=["refactor", "large_functions"])
    store_in_memory(refactor_out[:6000], "semantic", tags=["refactor", "candidates"])

    log("Step 3: Swarm to prioritize and summarize refactor suggestions")
    event_log = EventLog()
    swarm = Swarm(
        worker_count=2,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=get_memory_router(),
        use_tools=False,
    )
    task = (
        "Based on large-function and refactor-candidate analysis in memory, "
        "produce a short prioritized list of refactor suggestions: top 5–7 items with "
        "file/function name and one-line recommendation per item."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Refactor Suggestions")
    save_markdown(report, "refactor_suggestions.md")
    completed = swarm.last_completed_tasks
    save_json(
        {
            "large_functions_preview": large_out[:1500],
            "refactor_candidates_preview": refactor_out[:1500],
            "task_ids": [t.id for t in completed],
            "task_descriptions": [t.description or "" for t in completed],
        },
        "refactor_meta.json",
        normalize_strings=True,
    )
    print(report)
    log("Done.")


if __name__ == "__main__":
    main()
