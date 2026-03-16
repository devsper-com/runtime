#!/usr/bin/env python3
"""
Literature Review Pipeline: directory of research papers → structured review report.

Workflow: docproc extraction → corpus building → topic extraction → citation graph
→ swarm literature review. Uses tools, memory, and swarm runtime.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._config import get_planner_model, get_worker_model
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

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Literature review from a directory of papers")
    parser.add_argument("directory", nargs="?", default=".", help="Directory containing PDF/DOCX papers")
    parser.add_argument("--output", "-o", default=None, help="Output report path (default: examples/output/)")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if not directory.exists() or not directory.is_dir():
        log(f"Error: directory not found: {directory}")
        sys.exit(1)

    log("Literature Review Pipeline")
    log("Step 1: Docproc corpus pipeline (extract + corpus)")
    corpus_out = run_tool_safe("docproc_corpus_pipeline", {"directory": str(directory)})
    try:
        corpus_data = json.loads(corpus_out)
    except json.JSONDecodeError:
        corpus_data = {"documents": [], "total_files": 0}
    if not corpus_data.get("documents"):
        log("No documents extracted. Add PDF/DOCX files to the directory or use a sample.")
        corpus_data = {"documents": [{"title": "Sample", "path": "none", "sections": [], "word_count": 0, "citations": []}], "total_files": 0}

    log("Step 2: Topic extraction (document_topic_extractor on first doc if any file)")
    papers_dir = directory
    first_doc = None
    for ext in (".pdf", ".docx"):
        for p in papers_dir.rglob(f"*{ext}"):
            if p.is_file():
                first_doc = str(p)
                break
        if first_doc:
            break
    topic_out = ""
    if first_doc:
        topic_out = run_tool_safe("document_topic_extractor", {"file_path": first_doc, "top_n": 15})
    else:
        topic_out = "No document for topic extraction."

    log("Step 3: Citation graph (from discovered files)")
    file_paths = list(directory.rglob("*.pdf"))[:10] + list(directory.rglob("*.docx"))[:10]
    file_paths = [str(p) for p in file_paths if p.is_file()]
    if not file_paths:
        file_paths = [first_doc] if first_doc else []
    citation_out = run_tool_safe("citation_graph_builder", {"file_paths": file_paths}) if file_paths else "No files for citation graph."

    log("Step 4: Swarm literature review (batch planning)")
    texts = [d.get("title", "") + " " + str(d.get("sections", []))[:500] for d in corpus_data.get("documents", [])[:20]]
    if not texts:
        texts = ["Sample research context"]
    swarm_review_out = run_tool_safe("swarm_literature_review", {"texts": texts, "batch_size": 3, "top_keywords_per_batch": 5})

    store_in_memory(corpus_out[:8000], "research", tags=["literature_review", "corpus"])
    store_in_memory(topic_out[:4000], "semantic", tags=["literature_review", "topics"])
    store_in_memory(citation_out[:4000], "semantic", tags=["literature_review", "citations"])

    log("Step 5: Swarm synthesis (planner + executor)")
    event_log = EventLog()
    swarm = Swarm(
        worker_count=2,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=get_memory_router(),
        store_swarm_memory=True,
        use_tools=False,
    )
    task = (
        "Write a short structured literature review report (1–2 pages) based on the following. "
        "Include: (1) Overview of the corpus, (2) Main topics and themes, (3) Citation/related work notes, "
        "(4) Summary and conclusions. Use the relevant memory context provided."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Literature Review Report")
    out_path = args.output
    if not out_path:
        out_path = examples_output_dir() / "literature_review_report.md"
    else:
        out_path = Path(out_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(normalize_report_text(report), encoding="utf-8")
    log(f"Saved: {out_path}")

    completed = swarm.last_completed_tasks
    save_json(
        {
            "corpus_summary": {"total_files": corpus_data.get("total_files", 0), "documents": len(corpus_data.get("documents", []))},
            "swarm_literature_review": swarm_review_out[:2000],
            "task_ids": [t.id for t in completed],
            "task_descriptions": [t.description or "" for t in completed],
        },
        "literature_review_meta.json",
        normalize_strings=True,
    )
    log("Done.")


if __name__ == "__main__":
    main()
