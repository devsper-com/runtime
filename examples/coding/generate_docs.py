#!/usr/bin/env python3
"""
Codebase Documentation Generator: repo path → API extraction, docstring generation, architecture summary → markdown docs.

Workflow: api_surface_extractor → (optional docstring tool if present) → architecture_analyzer
→ swarm to generate markdown documentation. Uses tools, memory, swarm runtime.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import build_report_from_swarm, get_memory_router, log, run_tool_safe, save_markdown, store_in_memory
from examples._config import get_planner_model, get_worker_model

from hivemind.swarm.swarm import Swarm
from hivemind.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate documentation for a repository")
    parser.add_argument("path", nargs="?", default=".", help="Repository root path")
    args = parser.parse_args()
    repo = Path(args.path).resolve()
    if not repo.exists() or not repo.is_dir():
        log(f"Error: path not found: {repo}")
        sys.exit(1)

    log("Codebase Documentation Generator")
    log("Step 1: API surface extractor")
    api_out = run_tool_safe("api_surface_extractor", {"path": str(repo)})
    log("Step 2: Architecture analyzer")
    arch_out = run_tool_safe("architecture_analyzer", {"path": str(repo), "max_depth": 4})
    log("Step 3: Codebase indexer (for symbols)")
    index_out = run_tool_safe("codebase_indexer", {"path": str(repo), "max_depth": 4})

    store_in_memory(api_out[:8000], "semantic", tags=["docs", "api"])
    store_in_memory(arch_out[:6000], "semantic", tags=["docs", "architecture"])
    store_in_memory(index_out[:6000], "semantic", tags=["docs", "index"])

    log("Step 4: Swarm documentation synthesis")
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
        "Write markdown documentation for this codebase. Include: (1) Overview and architecture summary, "
        "(2) Main modules and their roles, (3) API surface summary (public functions/classes), "
        "(4) How to get started. Use the relevant memory context. Output in clear sections with headers."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Codebase Documentation")
    save_markdown(report, "codebase_documentation.md")
    log("Done.")


if __name__ == "__main__":
    main()
