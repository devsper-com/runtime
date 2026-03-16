#!/usr/bin/env python3
"""
Document Intelligence: directory of PDFs or DOCX → docproc extraction, concept frequency, knowledge graph, timeline → report.

Workflow: docproc extraction → concept_frequency → knowledge graph → timeline extraction
→ swarm document intelligence report. Uses tools, memory, knowledge graph, swarm runtime.
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

from devsper.knowledge.knowledge_graph import KnowledgeGraph
from devsper.memory.memory_store import get_default_store
from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Document intelligence from PDF/DOCX directory")
    parser.add_argument("directory", nargs="?", default=".", help="Directory containing documents")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if not directory.exists() or not directory.is_dir():
        log(f"Error: directory not found: {directory}")
        sys.exit(1)

    log("Document Intelligence")
    log("Step 1: Docproc corpus pipeline")
    corpus_out = run_tool_safe("docproc_corpus_pipeline", {"directory": str(directory)})
    try:
        corpus_data = json.loads(corpus_out)
        docs = corpus_data.get("documents", [])
    except json.JSONDecodeError:
        docs = []

    file_paths = []
    for ext in (".pdf", ".docx", ".md"):
        file_paths.extend([str(p) for p in directory.rglob(f"*{ext}") if p.is_file()][:15])
    concept_out = ""
    if file_paths:
        log("Step 2: Concept frequency analyzer")
        concept_out = run_tool_safe("concept_frequency_analyzer", {"file_paths": file_paths[:10], "top_n": 20})

    log("Step 3: Knowledge graph from corpus text")
    texts = []
    for d in docs[:5]:
        title = d.get("title", "")
        sections = d.get("sections", [])
        block = title + " " + " ".join(s.get("title", "") + " " + str(s.get("word_count", "")) for s in sections)
        texts.append(block[:3000])
    if not texts:
        texts = ["Sample document about project timeline and milestones."]
    kg_tool_out = run_tool_safe("research_graph_builder", {"documents": texts})

    store = get_default_store()
    from devsper.memory.memory_types import MemoryRecord, MemoryType
    from devsper.memory.memory_store import generate_memory_id
    from devsper.memory.memory_index import MemoryIndex
    for i, t in enumerate(texts[:3]):
        rec = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.RESEARCH,
            source_task="doc_intel",
            content=t[:8000],
            tags=["doc_intel", f"doc_{i}"],
        )
        idx = MemoryIndex(store)
        rec = idx.ensure_embedding(rec)
        store.store(rec)
    kg = KnowledgeGraph(store=store)
    kg.build_from_memory()
    kg_summary = {"nodes": kg.graph.number_of_nodes(), "edges": kg.graph.number_of_edges()}

    timeline_out = ""
    if file_paths:
        log("Step 4: Timeline extractor (first doc)")
        timeline_out = run_tool_safe("timeline_extractor", {"file_path": file_paths[0]})

    store_in_memory(corpus_out[:6000], "semantic", tags=["doc_intel", "corpus"])
    store_in_memory(concept_out[:4000] if concept_out else "No concepts.", "semantic", tags=["doc_intel", "concepts"])
    store_in_memory(kg_tool_out[:4000], "semantic", tags=["doc_intel", "kg"])

    log("Step 5: Swarm document intelligence report")
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
        "Write a short document intelligence report: (1) Corpus overview, (2) Main concepts and themes, "
        "(3) Key relationships (knowledge graph), (4) Timeline or sequence if present. Use memory context."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Document Intelligence Report")
    save_markdown(report, "document_intelligence_report.md")
    completed = swarm.last_completed_tasks
    save_json(
        {
            "corpus_docs": len(docs),
            "concept_preview": concept_out[:800] if concept_out else "",
            "kg_summary": kg_summary,
            "timeline_preview": timeline_out[:500] if timeline_out else "",
            "task_ids": [t.id for t in completed],
            "task_descriptions": [t.description or "" for t in completed],
        },
        "document_intelligence_meta.json",
        normalize_strings=True,
    )
    log("Done.")


if __name__ == "__main__":
    main()
