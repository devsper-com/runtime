"""
Hivemind CLI: run, tui, research, analyze, memory, init, doctor.

Usage:
    hivemind run "analyze diffusion models"
    hivemind init
    hivemind doctor
    hivemind tui
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    """Project root (examples/ parent) for running example scripts."""
    return Path(__file__).resolve().parent.parent.parent


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


def _run_init(no_interactive: bool = False) -> int:
    """Run init subcommand: create hivemind.toml, example workflow, dataset folder."""
    from hivemind.cli.init import run_init

    return run_init(interactive=not no_interactive)


def _run_doctor() -> int:
    """Run doctor subcommand: verify GITHUB_TOKEN, OpenAI, config, tools."""
    from hivemind.cli.init import run_doctor

    return run_doctor()


def _run_replay(run_id: str, events_dir: str | None) -> int:
    """Replay a swarm run by run_id; if run_id empty, list recent run IDs."""
    from hivemind.runtime.replay_engine import replay_run, list_run_ids

    if not run_id or not run_id.strip():
        try:
            from hivemind.config import get_config

            cfg = get_config()
            events_dir = events_dir or cfg.events_dir
        except Exception:
            events_dir = events_dir or ".hivemind/events"
        ids_ = list_run_ids(events_dir)
        if not ids_:
            print("No run logs found.", file=sys.stderr)
            return 0
        print("Recent run IDs (use: hivemind replay <run_id>):")
        for i in ids_[:20]:
            print(f"  {i}")
        return 0
    try:
        from hivemind.config import get_config

        cfg = get_config()
        events_dir = events_dir or cfg.events_dir
    except Exception:
        events_dir = events_dir or ".hivemind/events"
    transcript = replay_run(run_id.strip(), events_dir=events_dir)
    print(transcript)
    if "No event log found" in transcript or "Empty event log" in transcript:
        return 1
    return 0


def _run_graph(run_id: str | None) -> int:
    """Export task DAG for a run as Mermaid diagram. run_id optional (latest if omitted)."""
    from hivemind.config import get_config
    from hivemind.visualization.dag_export import (
        load_dag,
        export_mermaid,
        list_run_ids,
    )

    cfg = get_config()
    events_dir = cfg.events_dir
    if run_id is None or run_id.strip() == "":
        run_ids = list_run_ids(events_dir)
        if not run_ids:
            print(
                'No runs found. Run a swarm first (e.g. hivemind run "task").',
                file=sys.stderr,
            )
            return 1
        run_id = run_ids[0]
    nodes, edges = load_dag(events_dir, run_id.strip())
    if not nodes and not edges:
        print(f"No DAG found for run {run_id!r}.", file=sys.stderr)
        return 1
    print(export_mermaid(nodes, edges))
    return 0


def _run_analytics() -> int:
    """Show tool usage analytics: count, success rate, latency."""
    from hivemind.analytics import get_default_analytics

    stats = get_default_analytics().get_stats()
    if not stats:
        print("No tool usage recorded yet.")
        return 0
    for s in stats:
        print(
            f"{s['tool_name']}: count={s['count']} success_rate={s['success_rate']:.1f}% avg_latency_ms={s['avg_latency_ms']}"
        )
    return 0


def _run_cache(subcommand: str) -> int:
    """Cache subcommand: stats | clear."""
    from hivemind.cache import TaskCache

    cache = TaskCache()
    if subcommand == "stats":
        st = cache.stats()
        print(f"Cached task results: {st['entries']}")
        return 0
    if subcommand == "clear":
        cache.clear()
        print("Cache cleared.")
        return 0
    print("Usage: hivemind cache stats | hivemind cache clear", file=sys.stderr)
    return 1


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

    query_parser = subparsers.add_parser(
        "query", help="Query knowledge graph (entity search)"
    )
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

    init_parser = subparsers.add_parser(
        "init", help="Set up a new project (hivemind.toml, example workflow, dataset)"
    )
    init_parser.add_argument(
        "--no-interactive",
        "-y",
        action="store_true",
        help="Use defaults without prompting (e.g. for CI)",
    )
    init_parser.set_defaults(func=lambda a: _run_init(a.no_interactive))

    doctor_parser = subparsers.add_parser(
        "doctor", help="Verify environment (tokens, config, tool registry)"
    )
    doctor_parser.set_defaults(func=lambda a: _run_doctor())

    graph_parser = subparsers.add_parser(
        "graph", help="Export task DAG as Mermaid diagram"
    )
    graph_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="Run ID (default: latest)",
    )
    graph_parser.set_defaults(func=lambda a: _run_graph(a.run_id))

    analytics_parser = subparsers.add_parser(
        "analytics", help="Show tool usage analytics"
    )
    analytics_parser.set_defaults(func=lambda a: _run_analytics())

    cache_parser = subparsers.add_parser(
        "cache", help="Task result cache: stats or clear"
    )
    cache_parser.add_argument(
        "subcommand",
        nargs="?",
        default="stats",
        choices=["stats", "clear"],
        help="stats | clear",
    )
    cache_parser.set_defaults(func=lambda a: _run_cache(a.subcommand))

    replay_parser = subparsers.add_parser(
        "replay",
        help="Reconstruct swarm execution from event log (deterministic replay)",
    )
    replay_parser.add_argument(
        "run_id",
        nargs="?",
        default="",
        help="Run ID (from events log filename); list recent if omitted",
    )
    replay_parser.add_argument(
        "--events-dir",
        default=None,
        help="Events directory (default: config)",
    )
    replay_parser.set_defaults(func=lambda a: _run_replay(a.run_id, a.events_dir))

    args = parser.parse_args()
    if not args.command:
        return _run_tui()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
