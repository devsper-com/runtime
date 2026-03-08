#!/usr/bin/env python3
"""
Research Gap Finder: research corpus → concept frequency, trend analysis, rare topics → potential research questions.

Workflow: concept frequency → trend analysis → rare topic detection → swarm to suggest research questions.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import (
    build_report_from_swarm,
    examples_output_dir,
    get_memory_router,
    log,
    normalize_report_text,
    run_tool_safe,
    save_json,
    store_in_memory,
)
from examples._config import get_planner_model, get_worker_model

from hivemind.swarm.swarm import Swarm
from hivemind.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Research gap analysis from corpus")
    parser.add_argument("paths", nargs="*", default=[], help="Paths to papers (PDF/DOCX) or --directory")
    parser.add_argument("--directory", "-d", default=None, help="Directory to scan for documents")
    args = parser.parse_args()

    paths = list(args.paths)
    if args.directory:
        d = Path(args.directory).resolve()
        if d.exists() and d.is_dir():
            for ext in (".pdf", ".docx", ".md"):
                paths.extend([str(p) for p in d.rglob(f"*{ext}") if p.is_file()][:25])
    if not paths:
        log("No paths given. Creating a minimal demo with one markdown file.")
        demo = Path(__file__).resolve().parent.parent / "output" / "gap_demo.md"
        demo.parent.mkdir(parents=True, exist_ok=True)
        demo.write_text(
            "What is the best optimization method for neural networks? "
            "Recent work uses Adam. Few papers study convergence in low data regimes. "
            "How can we improve generalization? Transfer learning is under-explored.",
            encoding="utf-8",
        )
        paths = [str(demo)]

    log("Research Gap Analysis")
    log("Step 1: Concept frequency across documents")
    freq_out = run_tool_safe("concept_frequency_analyzer", {"file_paths": paths[:20], "top_n": 25})
    log("Step 2: Research gap finder (question phrases, rare terms)")
    gap_out = run_tool_safe("research_gap_finder", {"file_paths": paths[:20], "min_doc_freq": 2})

    store_in_memory(freq_out[:6000], "semantic", tags=["research_gap", "concept_frequency"])
    store_in_memory(gap_out[:6000], "research", tags=["research_gap", "gaps"])

    log("Step 3: Swarm to generate potential research questions")
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
        "Based on concept frequency and research gap analysis (see relevant memory), "
        "list 3–5 potential research questions that are under-explored or high-impact. "
        "One short paragraph per question."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Potential Research Questions")
    out_data = {
        "concept_frequency_preview": freq_out[:1500],
        "gap_finder_preview": gap_out[:1500],
        "task_ids": [t.id for t in swarm.last_completed_tasks],
        "task_descriptions": [t.description or "" for t in swarm.last_completed_tasks],
    }
    save_json(out_data, "research_gap_analysis.json", normalize_strings=True)
    md_path = examples_output_dir() / "research_gap_questions.md"
    md_path.write_text(normalize_report_text(report), encoding="utf-8")
    log(f"Saved: {md_path}")
    print(report)
    log("Done.")


if __name__ == "__main__":
    main()
