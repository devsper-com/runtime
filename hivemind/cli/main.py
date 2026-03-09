"""
Hivemind CLI: run, tui, research, analyze, memory, init, doctor, build.

Usage:
    hivemind run "analyze diffusion models"
    hivemind build "fastapi todo app"
    hivemind init
    hivemind doctor
    hivemind tui
"""

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


def _load_project_dotenv() -> None:
    """Load .env from the project directory (where hivemind.toml lives) so API keys are available."""
    try:
        from dotenv import load_dotenv
        from hivemind.config.config_loader import project_config_paths
        for p in project_config_paths():
            if p.is_file():
                load_dotenv(p.parent / ".env")
                break
    except Exception:
        pass


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


def _run_swarm(task: str, quiet: bool = False) -> int:
    """Run swarm with the given task string. If not quiet, show live progress on stderr."""
    from hivemind.config import get_config
    from hivemind.utils.event_logger import EventLog
    from hivemind.swarm.swarm import Swarm
    from hivemind.memory.memory_router import MemoryRouter
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex
    from hivemind.cli.run_progress import read_run_status

    cfg = get_config()
    event_log = EventLog(events_folder_path=cfg.events_dir)
    log_path = event_log.log_path
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    workers = getattr(cfg.swarm, "workers", 2)
    swarm = Swarm(
        worker_count=workers,
        worker_model=cfg.worker_model,
        planner_model=cfg.planner_model,
        event_log=event_log,
        memory_router=memory_router,
        use_tools=True,
    )
    results_holder: list[dict] = []

    def _run() -> None:
        results_holder.append(swarm.run(task))

    thread = threading.Thread(target=_run, daemon=False)
    thread.start()

    if not quiet:
        last_status = ""
        while thread.is_alive():
            status, running = read_run_status(log_path, worker_count=workers)
            line = status
            if len(running) > 1:
                line += f"  (parallel: {len(running)} tasks)"
            if line != last_status:
                print("\r  " + line.ljust(70), end="", file=sys.stderr, flush=True)
                last_status = line
            time.sleep(0.3)
        print(file=sys.stderr, flush=True)

    thread.join()
    results = results_holder[0] if results_holder else {}

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


def _workflow_dispatch(args: object) -> int:
    """Dispatch workflow list | validate | run | <name>."""
    a = args
    first = getattr(a, "first", None)
    second = getattr(a, "second", None)
    inputs = getattr(a, "input", None) or []
    if first == "list":
        return _workflow_list()
    if first == "validate":
        return _workflow_validate(second or "")
    if first == "run":
        return _workflow_run(second or "", inputs)
    if first:
        return _workflow_run(first, inputs)
    return _workflow_list()


def _workflow_list() -> int:
    """List all defined workflows with name, version, step count, description."""
    try:
        from rich.console import Console
        from rich.table import Table
        from hivemind.workflow.loader import list_workflows, load_workflow
    except ImportError:
        from hivemind.workflow.loader import list_workflows, load_workflow
        names = list_workflows()
        for n in names:
            wf = load_workflow(n)
            if wf:
                print(f"{wf.name}  v{wf.version}  steps={len(wf.steps)}  {wf.description or ''}")
        return 0
    console = Console()
    names = list_workflows()
    if not names:
        console.print("No workflows defined. Add [workflow] to workflow.hivemind.toml or hivemind.toml.")
        return 0
    table = Table(title="Workflows")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Steps", justify="right")
    table.add_column("Description", style="dim")
    for n in names:
        wf = load_workflow(n)
        if wf:
            table.add_row(
                wf.name,
                wf.version,
                str(len(wf.steps)),
                (wf.description or "")[:60],
            )
    console.print(table)
    return 0


def _workflow_validate(name: str) -> int:
    """Validate workflow by name. Exit 0 if valid, 1 if errors."""
    from hivemind.workflow.loader import load_workflow
    from hivemind.workflow.validator import ValidationReport, validate_workflow
    wf = load_workflow(name)
    if not wf:
        print(f"Workflow '{name}' not found.", file=sys.stderr)
        return 1
    report = validate_workflow(wf)
    try:
        from rich.console import Console
        from rich.markup import escape
        console = Console()
        if report.errors:
            for e in report.errors:
                console.print(f"[red]✗[/red] {escape(e)}")
        if report.warnings:
            for w in report.warnings:
                console.print(f"[yellow]⚠[/yellow] {escape(w)}")
        if report.info:
            for i in report.info:
                console.print(f"[dim]ℹ[/dim] {escape(i)}")
        if report.valid and not report.errors:
            console.print("[green]✓[/green] Validation passed.")
        elif report.errors:
            console.print("[red]✗[/red] Validation failed.")
    except ImportError:
        for e in report.errors:
            print(f"✗ {e}", file=sys.stderr)
        for w in report.warnings:
            print(f"⚠ {w}", file=sys.stderr)
        for i in report.info:
            print(f"ℹ {i}")
        if report.valid:
            print("✓ Validation passed.")
        else:
            print("✗ Validation failed.", file=sys.stderr)
    return 0 if report.valid else 1


def _workflow_run(name: str, input_pairs: list[str]) -> int:
    """Run workflow by name with optional --input key=value. Print summary table after."""
    from hivemind.config import get_config
    from hivemind.memory.memory_router import MemoryRouter
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex
    from hivemind.workflow.loader import load_workflow
    from hivemind.workflow.runner import WorkflowRunner
    wf = load_workflow(name)
    if not wf:
        print(f"Workflow '{name}' not found.", file=sys.stderr)
        return 1
    inputs = {}
    for pair in input_pairs:
        if "=" in pair:
            k, v = pair.split("=", 1)
            inputs[k.strip()] = v.strip()
        else:
            inputs[pair.strip()] = ""
    cfg = get_config()
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    runner = WorkflowRunner()
    try:
        ctx = runner.run(
            wf,
            inputs=inputs,
            worker_model=cfg.worker_model,
            worker_count=getattr(cfg.swarm, "workers", 2),
            memory_router=memory_router,
            use_tools=True,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Workflow run summary")
        table.add_column("Step", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Note", style="dim")
        for step_id, sr in ctx.steps.items():
            if sr.skipped:
                status = "[yellow]skipped[/yellow]"
            elif sr.error:
                status = "[red]failed[/red]"
            else:
                status = "[green]completed[/green]"
            table.add_row(
                step_id,
                status,
                f"{sr.duration_seconds:.2f}s",
                sr.error or ("(skipped)" if sr.skipped else ""),
            )
        console.print(table)
    except ImportError:
        for step_id, sr in ctx.steps.items():
            status = "skipped" if sr.skipped else ("failed" if sr.error else "completed")
            print(f"  {step_id}  {status}  {sr.duration_seconds:.2f}s  {sr.error or ''}")
    for step_id, sr in ctx.steps.items():
        if not sr.skipped and not sr.error and sr.raw_result:
            print(f"\n--- {step_id} ---")
            print((sr.raw_result or "")[:2000])
            if (sr.raw_result or "") and len(sr.raw_result) > 2000:
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


def _run_credentials(args: object) -> int:
    """Run credentials subcommand: set, list, delete, migrate."""
    from hivemind.credentials.cli import run_credentials

    return run_credentials(args)


def _run_doctor() -> int:
    """Run doctor subcommand: verify GITHUB_TOKEN, OpenAI, config, tools."""
    from hivemind.cli.init import run_doctor

    return run_doctor()


def _run_build(app_idea: str, output_dir: str) -> int:
    """Build a working repo from an app description (autonomous application builder)."""
    from hivemind.dev.builder import run_build as do_build

    out = output_dir or "./build_output"
    print(f"Building app: {app_idea!r}", file=sys.stderr)
    print(f"Output directory: {out}", file=sys.stderr)
    result = do_build(app_idea, out)
    if result.get("success"):
        print(f"Done. Repository at: {result['repo_path']}", file=sys.stderr)
        print(result["repo_path"])
        return 0
    print("Build completed with test failures.", file=sys.stderr)
    dr = result.get("debug_result")
    if dr and getattr(dr, "last_stdout", None):
        print(dr.last_stdout[:1500], file=sys.stderr)
    return 1


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
    try:
        from hivemind.tools.scoring import get_default_score_store
        from hivemind.tools.scoring.report import generate_tools_report
        store = get_default_score_store()
        scores = store.get_all_scores()
        if scores:
            print()
            print(generate_tools_report(scores))
    except Exception:
        pass
    return 0


def _run_tools(args: object) -> int:
    """List tools with reliability scores, or reset score history."""
    from rich.console import Console
    from rich.prompt import Confirm
    from rich.table import Table

    from hivemind.tools.registry import list_tools
    from hivemind.tools.selector import _tool_category
    from hivemind.tools.scoring import get_default_score_store
    from hivemind.tools.scoring.scorer import score_label

    subcommand = getattr(args, "tools_subcommand", None) or "list"
    category_filter = getattr(args, "category", None)
    poor_only = getattr(args, "poor", False)
    reset_all = getattr(args, "reset_all", False)
    tool_name_reset = getattr(args, "tool_name", None)

    if subcommand == "reset":
        store = get_default_score_store()
        if reset_all:
            if not Confirm.ask("Wipe all tool scores? This cannot be undone."):
                return 0
            store.reset(None)
            print("All tool scores wiped.")
            return 0
        if tool_name_reset:
            store.reset(tool_name_reset)
            print(f"Score history wiped for: {tool_name_reset}")
            return 0
        print("Usage: hivemind tools reset <tool_name> | hivemind tools reset --all", file=sys.stderr)
        return 1

    # List: all registered tools with scores
    store = get_default_score_store()
    scores_by_name = {s.tool_name: s for s in store.get_all_scores()}
    all_tools = list_tools()
    if category_filter:
        allowed = {category_filter.lower().strip()}
        all_tools = [t for t in all_tools if _tool_category(t) in allowed]
    rows: list[tuple[str, str, float, str, float, float, int, str, bool]] = []
    for t in all_tools:
        s = scores_by_name.get(t.name)
        if s is None:
            score_val = 0.75
            label = "new"
            success_rate = 0.0
            avg_lat = 0.0
            calls = 0
            last_used = "-"
            is_new = True
        else:
            score_val = s.composite_score
            label = score_label(s.composite_score)
            success_rate = s.success_rate
            avg_lat = s.avg_latency_ms
            calls = s.total_calls
            last_used = s.last_updated[:10] if len(s.last_updated) >= 10 else s.last_updated
            is_new = s.is_new
        if poor_only and score_val >= 0.40:
            continue
        cat = _tool_category(t)
        rows.append((t.name, cat, score_val, label, success_rate, avg_lat, calls, last_used, is_new))

    rows.sort(key=lambda r: -r[2])
    table = Table(title="Tool reliability scores")
    table.add_column("Tool Name", style="bold")
    table.add_column("Category")
    table.add_column("Score", justify="right")
    table.add_column("Label")
    table.add_column("Success Rate", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Calls", justify="right")
    table.add_column("Last Used")
    for r in rows:
        name, cat, score_val, label, success_rate, avg_lat, calls, last_used, is_new = r
        if is_new and label == "new":
            label_style = "dim"
        elif label == "excellent":
            label_style = "green"
        elif label == "good":
            label_style = "default"
        elif label == "degraded":
            label_style = "yellow"
        else:
            label_style = "red"
        table.add_row(
            name,
            cat,
            f"{score_val:.2f}",
            f"[{label_style}]{label}[/]",
            f"{success_rate:.0%}" if not is_new else "-",
            f"{avg_lat:.0f} ms" if not is_new else "-",
            str(calls),
            last_used,
        )
    console = Console()
    if rows:
        console.print(table)
    else:
        console.print("No tools match the filters.")
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


def _run_completion(parser: argparse.ArgumentParser, shell: str) -> int:
    """Print shell completion script."""
    try:
        import shtab

        print(shtab.complete(parser, shell=shell))
        return 0
    except ImportError:
        print("Install shtab: pip install shtab", file=sys.stderr)
        return 1


def _run_upgrade(args: object) -> int:
    """Run upgrade subcommand: check, changelog, install."""
    from hivemind.upgrade.cli import run_upgrade

    return run_upgrade(args)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].strip() == ".":
        sys.argv = [sys.argv[0]]

    # Non-blocking startup nag if update available (uses cache, ~100ms)
    try:
        from hivemind.upgrade.notifier import check_and_notify

        check_and_notify()
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="hivemind",
        description="Orchestrate distributed swarms of AI agents that collaboratively solve complex tasks.",
        epilog="""
Quick start:
  hivemind init                    # Set up a new project
  hivemind run "your task here"    # Run the swarm
  hivemind tui                     # Launch the terminal UI

Examples:
  hivemind run "Analyze diffusion models and summarize key papers"
  hivemind build "fastapi todo app" -o ./myapp
  hivemind credentials migrate     # Import API keys from .env
  hivemind doctor                  # Check your setup
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    try:
        import shtab

        shtab.add_argument_to(parser, ["--print-completion"])
    except ImportError:
        pass
    subparsers = parser.add_subparsers(dest="command", help="Command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run the swarm on a task",
        description="Decompose a task into subtasks and execute them with AI workers.",
        epilog="""
Examples:
  hivemind run "Summarize swarm intelligence in one paragraph"
  hivemind run "Analyze diffusion models" -q
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.add_argument(
        "task",
        nargs="?",
        default="Summarize swarm intelligence in one paragraph.",
        help="Task prompt",
    )
    run_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="No progress output; only print results (for piping)",
    )
    run_parser.set_defaults(func=lambda a: _run_swarm(a.task, a.quiet))

    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch terminal UI",
        description="Interactive dashboard for runs, memory, and analytics.",
        epilog="""
Examples:
  hivemind tui
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tui_parser.set_defaults(func=lambda a: _run_tui())

    research_parser = subparsers.add_parser(
        "research",
        help="Run literature review on a directory",
        description="Run the literature review example on a directory of papers.",
        epilog="""
Examples:
  hivemind research .
  hivemind research ./papers
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    research_parser.add_argument(
        "path", nargs="?", default=".", help="Directory with papers (PDF/DOCX)"
    )
    research_parser.set_defaults(func=lambda a: _run_research(a.path))

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze repository architecture",
        description="Run repository analysis to understand code structure and dependencies.",
        epilog="""
Examples:
  hivemind analyze .
  hivemind analyze /path/to/repo
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analyze_parser.add_argument(
        "path", nargs="?", default=".", help="Repository root path"
    )
    analyze_parser.set_defaults(func=lambda a: _run_analyze(a.path))

    memory_parser = subparsers.add_parser(
        "memory",
        help="List memory entries",
        description="List stored memory entries from past swarm runs.",
        epilog="""
Examples:
  hivemind memory
  hivemind memory -n 50
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    memory_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Max entries to show"
    )
    memory_parser.set_defaults(func=lambda a: _run_memory(a.limit))

    query_parser = subparsers.add_parser(
        "query",
        help="Query knowledge graph",
        description="Search entities and relationships in the knowledge graph built from memory.",
        epilog="""
Examples:
  hivemind query "diffusion models"
  hivemind query "machine learning"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    query_parser.add_argument(
        "query_text",
        nargs="?",
        default="",
        help="Query string (e.g. diffusion models)",
    )
    query_parser.set_defaults(func=lambda a: _run_query(a.query_text))

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="List, validate, or run workflows",
        description="List, validate, or run workflows from workflow.hivemind.toml.",
        epilog="""
Examples:
  hivemind workflow list
  hivemind workflow validate my_workflow
  hivemind workflow run my_workflow --input text="hello"
  hivemind workflow my_workflow
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_parser.add_argument(
        "first",
        nargs="?",
        help="Subcommand: list | validate | run; or workflow name to run",
    )
    workflow_parser.add_argument(
        "second",
        nargs="?",
        help="Workflow name (for validate/run)",
    )
    workflow_parser.add_argument(
        "--input",
        action="append",
        metavar="KEY=VALUE",
        help="Runtime input (repeat for multiple). Used with run.",
    )
    workflow_parser.set_defaults(func=_workflow_dispatch)

    init_parser = subparsers.add_parser(
        "init",
        help="Set up a new project",
        description="Create hivemind.toml, configure providers, and optionally store API keys securely.",
        epilog="""
Examples:
  hivemind init
  hivemind init -y
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    init_parser.add_argument(
        "--no-interactive",
        "-y",
        action="store_true",
        help="Use defaults without prompting (e.g. for CI)",
    )
    init_parser.set_defaults(func=lambda a: _run_init(a.no_interactive))

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Verify environment",
        description="Check API keys, config files, tool registry, and security (e.g. plaintext keys in TOML).",
        epilog="""
Examples:
  hivemind doctor
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doctor_parser.set_defaults(func=lambda a: _run_doctor())

    graph_parser = subparsers.add_parser(
        "graph",
        help="Export task DAG as Mermaid",
        description="Export the task dependency graph for a run as a Mermaid diagram.",
        epilog="""
Examples:
  hivemind graph
  hivemind graph abc123-run-id
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    graph_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="Run ID (default: latest)",
    )
    graph_parser.set_defaults(func=lambda a: _run_graph(a.run_id))

    analytics_parser = subparsers.add_parser(
        "analytics",
        help="Show tool usage analytics",
        description="Display tool usage stats: count, success rate, and latency.",
        epilog="""
Examples:
  hivemind analytics
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analytics_parser.set_defaults(func=lambda a: _run_analytics())

    tools_parser = subparsers.add_parser(
        "tools",
        help="List tool reliability scores or reset history",
        description="List registered tools with reliability scores (excellent/good/degraded/poor), or reset score history.",
        epilog="""
Examples:
  hivemind tools
  hivemind tools --category research
  hivemind tools --poor
  hivemind tools reset my_tool
  hivemind tools reset --all
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tools_parser.add_argument(
        "tools_subcommand",
        nargs="?",
        default="list",
        choices=["list", "reset"],
        help="list (default) | reset",
    )
    tools_parser.add_argument(
        "tool_name",
        nargs="?",
        help="Tool name (for reset)",
    )
    tools_parser.add_argument(
        "--category",
        metavar="NAME",
        help="Filter by category",
    )
    tools_parser.add_argument(
        "--poor",
        action="store_true",
        help="Show only tools with score < 0.40",
    )
    tools_parser.add_argument(
        "--all",
        dest="reset_all",
        action="store_true",
        help="Wipe all scores (with confirmation; use with reset)",
    )
    tools_parser.set_defaults(func=_run_tools)

    cache_parser = subparsers.add_parser(
        "cache",
        help="Task result cache",
        description="View or clear the task result cache.",
        epilog="""
Examples:
  hivemind cache stats
  hivemind cache clear
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cache_parser.add_argument(
        "subcommand",
        nargs="?",
        default="stats",
        choices=["stats", "clear"],
        help="stats | clear",
    )
    cache_parser.set_defaults(func=lambda a: _run_cache(a.subcommand))

    build_parser = subparsers.add_parser(
        "build",
        help="Build an app from a description",
        description="Autonomous application builder: generate a working repo from an app description.",
        epilog="""
Examples:
  hivemind build "fastapi todo app"
  hivemind build "CLI tool for CSV analysis" -o ./csv-tool
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    build_parser.add_argument(
        "app_idea",
        nargs="?",
        default="fastapi todo app",
        help="App description (e.g. 'fastapi todo app')",
    )
    build_parser.add_argument(
        "-o",
        "--output",
        default="./build_output",
        help="Output directory for the generated repo (default: ./build_output)",
    )
    build_parser.set_defaults(func=lambda a: _run_build(a.app_idea, a.output))

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a swarm run",
        description="Reconstruct swarm execution from the event log (deterministic replay).",
        epilog="""
Examples:
  hivemind replay
  hivemind replay abc123-run-id
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    credentials_parser = subparsers.add_parser(
        "credentials",
        help="Manage API keys and credentials",
        description="Store, list, and migrate credentials securely (OS keychain only).",
        epilog="""
Examples:
  hivemind credentials set openai api_key
  hivemind credentials list
  hivemind credentials migrate
  hivemind credentials export azure    # print env KEY=value for sourcing
  hivemind credentials delete openai api_key
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    credentials_parser.add_argument(
        "credentials_subcommand",
        nargs="?",
        choices=["set", "list", "delete", "migrate", "export"],
        help="set | list | delete | migrate | export",
    )
    credentials_parser.add_argument(
        "provider",
        nargs="?",
        help="Provider (e.g. openai, anthropic)",
    )
    credentials_parser.add_argument(
        "key",
        nargs="?",
        help="Key name (e.g. api_key)",
    )
    credentials_parser.set_defaults(func=lambda a: _run_credentials(a))

    completion_parser = subparsers.add_parser(
        "completion",
        help="Generate shell completion script",
        description="Print shell completion script for bash or zsh. Add to your shell config to enable tab completion.",
        epilog="""
Examples:
  # Bash - add to ~/.bashrc or ~/.bash_profile
  eval "$(hivemind completion bash)"

  # Zsh - add to ~/.zshrc
  eval "$(hivemind completion zsh)"

  # Or install to a file (bash)
  hivemind completion bash > ~/.local/share/bash-completion/completions/hivemind
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh"],
        help="Shell type",
    )
    completion_parser.set_defaults(func=lambda a: _run_completion(parser, a.shell))

    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Check for updates and upgrade",
        description="Check for updates and upgrade hivemind-ai from PyPI.",
        epilog="""
Examples:
  hivemind upgrade
  hivemind upgrade --check
  hivemind upgrade -y
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    upgrade_parser.add_argument(
        "--check",
        action="store_true",
        help="Only check and display if update is available",
    )
    upgrade_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    upgrade_parser.add_argument(
        "--version",
        metavar="VERSION",
        default=None,
        help="Install a specific version (e.g. 1.2.3)",
    )
    upgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without installing",
    )
    upgrade_parser.set_defaults(func=_run_upgrade)

    _load_project_dotenv()
    args = parser.parse_args()
    if not args.command:
        return _run_tui()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
