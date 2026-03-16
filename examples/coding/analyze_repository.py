#!/usr/bin/env python3
"""
Repository Analyzer: repo path → codebase index, dependency graph, architecture, API surface → architecture report.

Workflow: codebase_indexer → dependency_graph_builder → architecture_analyzer → api_surface_extractor
→ swarm synthesis. Uses tools, memory, provider routing.
"""

import argparse
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
    parser = argparse.ArgumentParser(description="Analyze repository architecture")
    parser.add_argument("path", nargs="?", default=".", help="Repository root path")
    args = parser.parse_args()
    repo = Path(args.path).resolve()
    if not repo.exists() or not repo.is_dir():
        log(f"Error: path not found or not a directory: {repo}")
        sys.exit(1)

    log("Repository Analyzer")
    log("Step 1: Codebase indexer")
    index_out = run_tool_safe("codebase_indexer", {"path": str(repo), "max_depth": 5})
    log("Step 2: Dependency graph builder")
    dep_out = run_tool_safe("dependency_graph_builder", {"path": str(repo)})
    log("Step 3: Architecture analyzer")
    arch_out = run_tool_safe("architecture_analyzer", {"path": str(repo), "max_depth": 3})
    log("Step 4: API surface extractor")
    api_out = run_tool_safe("api_surface_extractor", {"path": str(repo)})

    store_in_memory(index_out[:8000], "semantic", tags=["repo", "index"])
    store_in_memory(arch_out[:6000], "semantic", tags=["repo", "architecture"])
    store_in_memory(api_out[:6000], "semantic", tags=["repo", "api"])

    log("Step 5: Swarm architecture report")
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
        "Write a concise architecture report (about 1 page) for this codebase. "
        "Include: (1) High-level structure and entry points, (2) Main modules and dependencies, "
        "(3) API surface summary, (4) Recommendations. Use the relevant memory context."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Architecture Report")
    save_markdown(report, "architecture_report.md")
    completed = swarm.last_completed_tasks
    save_json(
        {
            "index_preview": index_out[:1200],
            "dependency_preview": dep_out[:1200],
            "architecture_raw": arch_out[:2000],
            "api_preview": api_out[:1200],
            "task_ids": [t.id for t in completed],
            "task_descriptions": [t.description or "" for t in completed],
        },
        "architecture_meta.json",
        normalize_strings=True,
    )
    log("Done.")


if __name__ == "__main__":
    main()
