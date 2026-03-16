#!/usr/bin/env python3
"""
Research Knowledge Graph: multiple papers or markdown files → entities, KG, visualization summary.

Workflow: extract entities → build knowledge graph → output JSON graph + printed summary.
Uses tools (research_graph_builder, knowledge_graph_extractor), memory, and knowledge graph.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import (
    get_memory_router,
    log,
    run_tool_safe,
    save_json,
)
from examples._config import get_planner_model, get_worker_model

from devsper.knowledge.knowledge_graph import KnowledgeGraph
from devsper.memory.memory_store import get_default_store
from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Build research knowledge graph from papers or markdown")
    parser.add_argument("paths", nargs="*", default=[], help="Paths to papers (PDF/DOCX) or markdown files")
    parser.add_argument("--directory", "-d", default=None, help="Or directory to scan for documents")
    args = parser.parse_args()

    paths = list(args.paths)
    if args.directory:
        d = Path(args.directory).resolve()
        if d.exists() and d.is_dir():
            for ext in (".pdf", ".docx", ".md", ".txt"):
                paths.extend([str(p) for p in d.rglob(f"*{ext}") if p.is_file()][:30])
    if not paths:
        log("No paths given. Using inline sample document for demo.")
        sample = """
        Machine learning methods have improved over time. The transformer approach
        is widely used. BERT and GPT are well-known models. Researchers use
        datasets like ImageNet and COCO. The diffusion model has become popular.
        """
        paths = []

    log("Research Knowledge Graph")
    documents_text = []
    for p in paths[:20]:
        path = Path(p).resolve()
        if not path.exists():
            continue
        if path.suffix.lower() in (".md", ".txt"):
            try:
                documents_text.append(path.read_text(encoding="utf-8", errors="replace")[:15000])
            except Exception:
                continue
        else:
            out = run_tool_safe("extract_document_text", {"file_path": str(path)})
            if out and "Error" not in out[:50]:
                documents_text.append(out[:15000])

    if not documents_text and not paths:
        documents_text = [
            "Machine learning methods have improved. The transformer approach is widely used. "
            "BERT and GPT are well-known models. Datasets like ImageNet and COCO are common. "
            "The diffusion model has become popular for generative tasks."
        ]

    if not documents_text:
        log("No document text extracted. Add PDF/DOCX/MD paths or --directory.")
        documents_text = ["Sample research document about machine learning and transformers."]

    log("Step 1: Research graph builder (entities, citations, methods, datasets)")
    graph_tool_out = run_tool_safe("research_graph_builder", {"documents": documents_text})
    try:
        graph_data = json.loads(graph_tool_out)
    except json.JSONDecodeError:
        graph_data = {"nodes": [], "edges": [], "entity_types": {}}

    log("Step 2: Store in memory and build KnowledgeGraph from memory")
    store = get_default_store()
    from devsper.memory.memory_types import MemoryRecord, MemoryType
    from devsper.memory.memory_store import generate_memory_id
    from devsper.memory.memory_index import MemoryIndex
    for i, text in enumerate(documents_text[:5]):
        rec = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.RESEARCH,
            source_task="research_graph",
            content=text[:10000],
            tags=["research_graph", f"doc_{i}"],
        )
        index = MemoryIndex(store)
        rec = index.ensure_embedding(rec)
        store.store(rec)

    kg = KnowledgeGraph(store=store)
    kg.build_from_memory()
    g = kg.graph
    nodes_list = list(g.nodes(data=True))[:50]
    edges_list = list(g.edges(data=True))[:80]
    kg_summary = {
        "nodes_sample": [{"id": n, **d} for n, d in nodes_list],
        "edges_sample": [{"u": u, "v": v, **d} for u, v, d in edges_list],
        "num_nodes": g.number_of_nodes(),
        "num_edges": g.number_of_edges(),
    }

    log("Step 3: Swarm summary of relationships")
    event_log = EventLog()
    swarm = Swarm(
        worker_count=1,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=get_memory_router(),
        use_tools=False,
    )
    summary_task = (
        "Summarize the research knowledge graph in 3–5 sentences: main entities, "
        "relationships, and how they connect. Be concise."
    )
    results = swarm.run(summary_task)
    summary_text = next(iter(results.values()), "") if results else ""

    out_data = {
        "tool_graph": graph_data,
        "knowledge_graph_summary": kg_summary,
        "swarm_summary": summary_text,
    }
    path = save_json(out_data, "research_graph.json")
    log("Printed summary:")
    print(summary_text or "(no swarm output)")
    log(f"JSON graph saved: {path}")
    log("Done.")


if __name__ == "__main__":
    main()
