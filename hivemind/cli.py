"""
Hivemind CLI: run, tui, research, analyze, memory.

Usage:
    hivemind run "analyze diffusion models"
    hivemind research papers/
    hivemind tui
    hivemind analyze path/to/repo
    hivemind memory [--limit N]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    """Project root (examples/ parent) for running example scripts."""
    return Path(__file__).resolve().parent.parent


def _run_example(script_path: Path, *args: str) -> int:
    """Run an example script with project root on PYTHONPATH."""
    root = _project_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, str(script_path)] + list(args)
    return subprocess.run(cmd, cwd=str(root), env=env).returncode


def _run_swarm(task: str) -> int:
    """Run swarm with the given task string."""
    from hivemind.config import get_config
    from hivemind.utils.event_logger import EventLog
    from hivemind.swarm.swarm import Swarm
    from hivemind.memory.memory_router import MemoryRouter
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex

    cfg = get_config()
    event_log = EventLog(events_folder_path=cfg.events_dir)
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    swarm = Swarm(
        worker_count=2,
        worker_model=cfg.worker_model,
        planner_model=cfg.planner_model,
        event_log=event_log,
        memory_router=memory_router,
        use_tools=True,
    )
    results = swarm.run(task)
    for task_id, result in results.items():
        print(f"--- {task_id} ---")
        print((result or "")[:2000])
        if (result or "") and len(result) > 2000:
            print("...")
    return 0


def _run_tui() -> int:
    """Launch the TUI."""
    from hivemind.config import get_config
    from hivemind.tui.app import run_tui

    cfg = get_config()
    run_tui(events_folder=cfg.events_dir)
    return 0


def _run_research(path: str) -> int:
    """Run literature review example on a directory."""
    root = _project_root()
    script = root / "examples" / "research" / "literature_review.py"
    if not script.exists():
        print(
            "Error: examples/research/literature_review.py not found", file=sys.stderr
        )
        return 1
    return _run_example(script, path or ".")


def _run_analyze(path: str) -> int:
    """Run repository analysis example."""
    root = _project_root()
    script = root / "examples" / "coding" / "analyze_repository.py"
    if not script.exists():
        print("Error: examples/coding/analyze_repository.py not found", file=sys.stderr)
        return 1
    return _run_example(script, path or ".")


def _run_workflow_cmd(name: str) -> int:
    """Run a workflow by name (from workflow.hivemind.toml)."""
    from hivemind.config import get_config
    from hivemind.memory.memory_router import MemoryRouter
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex
    from hivemind.workflow.loader import load_workflow
    from hivemind.workflow.runner import run_workflow

    wf = load_workflow(name)
    if not wf or not wf.get("steps"):
        print(f"Workflow '{name}' not found or has no steps.", file=sys.stderr)
        return 1
    cfg = get_config()
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    results = run_workflow(
        steps=wf["steps"],
        worker_model=cfg.worker_model,
        worker_count=getattr(cfg.swarm, "workers", 2),
        memory_router=memory_router,
        use_tools=True,
    )
    for task_id, result in results.items():
        print(f"--- {task_id} ---")
        print((result or "")[:2000])
        if (result or "") and len(result) > 2000:
            print("...")
    return 0


def _run_query(query_str: str) -> int:
    """Query the knowledge graph: entity search and relationship traversal."""
    from hivemind.knowledge.knowledge_graph import KnowledgeGraph
    from hivemind.knowledge.query import query as kg_query
    from hivemind.memory.memory_store import get_default_store

    store = get_default_store()
    kg = KnowledgeGraph(store=store)
    kg.build_from_memory()
    result = kg_query(kg, query_str or "")
    if not result.entities and not result.edges and not result.documents:
        print("No matching entities or documents.")
        return 0
    if result.entities:
        print("Entities:")
        for node_id, label in result.entities[:30]:
            print(f"  {node_id}  {label[:80]}")
    if result.edges:
        print("\nRelationships:")
        for a, b, et in result.edges[:30]:
            print(f"  {a} --[{et}]--> {b}")
    if result.documents:
        print("\nDocuments mentioning query:")
        for doc_id in result.documents[:20]:
            print(f"  {doc_id}")
    return 0


def _run_memory(limit: int) -> int:
    """List memory entries from the default store."""
    from hivemind.memory.memory_store import get_default_store

    store = get_default_store()
    records = store.list_memory(limit=limit)
    if not records:
        print("No memory entries.")
        return 0
    for r in records:
        tags = ", ".join(r.tags[:8]) if r.tags else "-"
        summary = (r.content or "")[:200] + (
            "..." if len(r.content or "") > 200 else ""
        )
        print(f"[{r.memory_type.value}] {r.id}")
        print(f"  tags: {tags}")
        print(f"  {summary}")
        print()
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].strip() == ".":
        sys.argv = [sys.argv[0]]

    parser = argparse.ArgumentParser(
        prog="hivemind",
        description="Distributed AI Swarm Runtime",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    run_parser = subparsers.add_parser("run", help="Run swarm with a task")
    run_parser.add_argument(
        "task",
        nargs="?",
        default="Summarize swarm intelligence in one paragraph.",
        help="Task prompt",
    )
    run_parser.set_defaults(func=lambda a: _run_swarm(a.task))

    tui_parser = subparsers.add_parser("tui", help="Launch terminal UI")
    tui_parser.set_defaults(func=lambda a: _run_tui())

    research_parser = subparsers.add_parser(
        "research", help="Run literature review on a directory"
    )
    research_parser.add_argument(
        "path", nargs="?", default=".", help="Directory with papers (PDF/DOCX)"
    )
    research_parser.set_defaults(func=lambda a: _run_research(a.path))

    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze repository architecture"
    )
    analyze_parser.add_argument(
        "path", nargs="?", default=".", help="Repository root path"
    )
    analyze_parser.set_defaults(func=lambda a: _run_analyze(a.path))

    memory_parser = subparsers.add_parser("memory", help="List memory entries")
    memory_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Max entries to show"
    )
    memory_parser.set_defaults(func=lambda a: _run_memory(a.limit))

    query_parser = subparsers.add_parser("query", help="Query knowledge graph (entity search)")
    query_parser.add_argument(
        "query_text",
        nargs="?",
        default="",
        help="Query string (e.g. diffusion models)",
    )
    query_parser.set_defaults(func=lambda a: _run_query(a.query_text))

    workflow_parser = subparsers.add_parser("workflow", help="Run a workflow by name")
    workflow_parser.add_argument(
        "name",
        help="Workflow name (e.g. research_pipeline)",
    )
    workflow_parser.set_defaults(func=lambda a: _run_workflow_cmd(a.name))

    args = parser.parse_args()
    if not args.command:
        return _run_tui()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
