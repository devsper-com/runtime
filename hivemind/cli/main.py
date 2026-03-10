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
import json
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


def _run_analyze_dispatch(args: object) -> int:
    """Dispatch: run_id -> run analysis; path (., /path) -> repo analysis."""
    run_id_or_path = getattr(args, "run_id_or_path", None)
    no_ai = getattr(args, "no_ai", False)
    json_out = getattr(args, "analyze_json", False)
    if run_id_or_path is None or (isinstance(run_id_or_path, str) and not run_id_or_path.strip()):
        from rich.console import Console
        from hivemind.runtime.run_history import RunHistory
        console = Console()
        rows = RunHistory().list_runs(limit=5)
        if rows:
            console.print("Recent runs (use [cyan]hivemind analyze <run_id>[/] for run analysis):")
            for r in rows[:5]:
                console.print(f"  [dim]{r.run_id}[/]")
        else:
            console.print("No runs yet. Use [cyan]hivemind analyze <run_id>[/] after a run, or [cyan]hivemind analyze .[/] for repo analysis.")
        return 0
    s = str(run_id_or_path).strip()
    if s in (".", "..") or "/" in s or os.path.exists(s):
        return _run_analyze(s)
    return _run_analyze_run(s, no_ai=no_ai, json_output=json_out)


def _run_analyze_run(
    run_id: str,
    no_ai: bool = False,
    json_output: bool = False,
) -> int:
    """Analyze a swarm run: load events, build report, optional LLM analysis."""
    from hivemind.config import get_config
    from hivemind.intelligence.analysis import (
        build_report_from_events,
        analyze,
        print_run_report,
        RunReport,
    )
    from hivemind.intelligence.analysis.cost_estimator import CostEstimator
    from rich.console import Console
    from rich.panel import Panel

    cfg = get_config()
    events_dir = cfg.events_dir
    console = Console()

    try:
        report = build_report_from_events(run_id, events_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        return 1
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        return 1

    if json_output:
        import json
        from dataclasses import asdict
        from hivemind.intelligence.analysis.run_report import TaskSummary
        def _serialize(obj):
            if hasattr(obj, "value"):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize(getattr(obj, k)) for k in obj.__dataclass_fields__}
            return obj
        out = {
            "run_id": report.run_id,
            "root_task": report.root_task,
            "strategy": report.strategy,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "total_duration_seconds": report.total_duration_seconds,
            "total_tasks": report.total_tasks,
            "completed_tasks": report.completed_tasks,
            "failed_tasks": report.failed_tasks,
            "skipped_tasks": report.skipped_tasks,
            "critical_path": report.critical_path,
            "bottleneck_task_id": report.bottleneck_task_id,
            "tools_called": report.tools_called,
            "tool_success_rate": report.tool_success_rate,
            "estimated_cost_usd": report.estimated_cost_usd,
            "models_used": report.models_used,
            "peak_parallelism": report.peak_parallelism,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "role": t.role,
                    "status": _serialize(t.status),
                    "duration_seconds": t.duration_seconds,
                    "tools_used": t.tools_used,
                    "tool_failures": t.tool_failures,
                    "tokens_used": t.tokens_used,
                    "retry_count": t.retry_count,
                    "error": t.error,
                }
                for t in report.tasks
            ],
        }
        console.print(json.dumps(out, indent=2))
        return 0

    print_run_report(report, console)
    if not no_ai:
        worker_model = getattr(cfg, "worker_model", None) or getattr(cfg.models, "worker", "gpt-4o-mini")
        from hivemind.utils.models import resolve_model
        worker_model = resolve_model(worker_model, "analysis")
        analysis_text = analyze(
            report,
            worker_model,
            stream_callback=lambda c: console.print(c, end=""),
        )
        report.plain_english_analysis = analysis_text
        console.print()
        console.print(Panel(analysis_text, title="Plain-English Analysis", border_style="dim"))
    return 0


def _run_runs(args: object) -> int:
    """List run history (Rich table) or run-analyze <run_id> --no-ai when run_id given."""
    run_id = getattr(args, "run_id", None)
    if run_id and str(run_id).strip():
        return _run_analyze_run(str(run_id).strip(), no_ai=True, json_output=False)
    from hivemind.runtime.run_history import RunHistory
    limit = getattr(args, "limit", 20)
    failed = getattr(args, "failed", False)
    json_out = getattr(args, "runs_json", False)
    history = RunHistory()
    filter_status = "failed" if failed else None
    rows = history.list_runs(limit=limit, filter_status=filter_status)
    if json_out:
        import json
        out = [
            {
                "run_id": r.run_id,
                "root_task": r.root_task[:200],
                "strategy": r.strategy,
                "started_at": r.started_at,
                "duration_seconds": r.duration_seconds,
                "total_tasks": r.total_tasks,
                "completed_tasks": r.completed_tasks,
                "failed_tasks": r.failed_tasks,
                "estimated_cost_usd": r.estimated_cost_usd,
            }
            for r in rows
        ]
        print(json.dumps(out, indent=2))
        return 0
    from rich.console import Console
    from rich.table import Table
    console = Console()
    table = Table(title="Run history")
    table.add_column("Run ID", style="dim", max_width=36, overflow="fold")
    table.add_column("Task", max_width=40, overflow="fold")
    table.add_column("Strategy", width=10)
    table.add_column("Status", width=14)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Tasks", justify="right", width=6)
    table.add_column("Cost", justify="right", width=10)
    table.add_column("Date", style="dim", width=24)
    for r in rows:
        short_id = r.run_id[:32] + "…" if len(r.run_id) > 32 else r.run_id
        task_preview = (r.root_task or "")[:40] + ("…" if len(r.root_task or "") > 40 else "")
        if r.failed_tasks > 0 and r.completed_tasks > 0:
            status = "[yellow]⚠ partial[/]"
        elif r.failed_tasks > 0:
            status = "[red]✗ failed[/]"
        else:
            status = "[green]✓ completed[/]"
        dur = f"{r.duration_seconds:.1f}s"
        tasks = f"{r.completed_tasks}/{r.total_tasks}"
        cost = f"${r.estimated_cost_usd:.4f}" if r.estimated_cost_usd is not None else "—"
        date = (r.started_at or "")[:24]
        table.add_row(short_id, task_preview, r.strategy or "—", status, dur, tasks, cost, date)
    if rows:
        console.print(table)
    else:
        console.print("No runs recorded. Run a swarm first (e.g. [cyan]hivemind run \"task\"[/]).")
    return 0


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


def _run_mcp_list() -> int:
    """List configured MCP servers and their tool counts (from live discovery)."""
    from hivemind.config import get_config
    from hivemind.tools.mcp import discover_mcp_tools
    cfg = get_config()
    servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="MCP servers")
        table.add_column("Name", style="cyan")
        table.add_column("Transport", style="dim")
        table.add_column("Tools", justify="right")
        for s in servers:
            sname = getattr(s, "name", "?")
            try:
                adapters = discover_mcp_tools(s)
                count = len(adapters)
            except Exception:
                count = "—"
            table.add_row(sname, getattr(s, "transport", "?"), str(count))
        if not servers:
            console.print("No MCP servers configured. Add [[mcp.servers]] to hivemind.toml or use [cyan]hivemind mcp add[/].")
        else:
            console.print(table)
    except ImportError:
        for s in servers:
            print(getattr(s, "name", "?"), getattr(s, "transport", "?"))
    return 0


def _run_mcp_test(server_name: str) -> int:
    """Connect to server, list tools, print names and descriptions. Exit 1 if connection fails."""
    from hivemind.config import get_config
    cfg = get_config()
    servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
    server = next((s for s in servers if getattr(s, "name", "") == server_name), None)
    if not server:
        print(f"Error: MCP server '{server_name}' not found in config.", file=sys.stderr)
        return 1
    try:
        from hivemind.tools.mcp import discover_mcp_tools
        adapters = discover_mcp_tools(server)
        print(f"Connected to '{server_name}'. Tools: {len(adapters)}")
        for a in adapters:
            print(f"  - {getattr(a, '_mcp_tool_name', a.name)}: {(a.description or '')[:80]}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_mcp_add() -> int:
    """Interactive: prompt for transport, command/url, name; append to hivemind.toml [mcp.servers]."""
    from pathlib import Path
    from hivemind.config.config_loader import project_config_paths
    config_path = None
    for p in project_config_paths():
        if p.is_file():
            config_path = p
            break
    if not config_path:
        print("Error: No hivemind.toml found. Run [cyan]hivemind init[/] first.", file=sys.stderr)
        return 1
    try:
        name = input("Server name (e.g. filesystem): ").strip() or "mcp-server"
        transport = input("Transport (stdio|http|sse) [stdio]: ").strip().lower() or "stdio"
        if transport == "stdio":
            cmd_str = input("Command (space-separated, e.g. npx -y @modelcontextprotocol/server-filesystem /tmp): ").strip()
            command = cmd_str.split() if cmd_str else []
            url = None
        else:
            command = None
            url = input("URL (e.g. http://localhost:3000): ").strip() or None
        toml = config_path.read_text()
        # Append [[mcp.servers]] entry
        entry = f'\n[[mcp.servers]]\nname = "{name}"\ntransport = "{transport}"\n'
        if command:
            entry += f'command = {json.dumps(command)}\n'
        if url:
            entry += f'url = "{url}"\n'
        if "\n[mcp]" not in toml and "[[mcp.servers]]" not in toml:
            toml = toml.rstrip() + "\n\n[mcp]\n" + entry.lstrip()
        else:
            toml = toml.rstrip() + "\n" + entry
        config_path.write_text(toml)
        print(f"Added MCP server '{name}' to {config_path}.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_a2a_serve(port: int | None) -> int:
    """Start A2A server, print AgentCard URL."""
    from hivemind.config import get_config
    from hivemind.agents.a2a.server import run_a2a_server
    cfg = get_config()
    p = port if port is not None else getattr(getattr(cfg, "a2a", None), "serve_port", 8080)
    swarm_name = getattr(getattr(cfg, "swarm", None), "name", None) or "hivemind"
    print(f"A2A server starting at http://localhost:{p}", file=sys.stderr)
    print(f"AgentCard: http://localhost:{p}/.well-known/agent.json", file=sys.stderr)
    run_a2a_server(host="0.0.0.0", port=p, swarm_name=swarm_name or "")
    return 0


def _run_a2a_discover(url: str) -> int:
    """Fetch AgentCard, print skills, optionally add to config."""
    try:
        from hivemind.agents.a2a.client import A2AClient
        client = A2AClient()
        import asyncio
        card = asyncio.run(client.get_agent_card(url))
        print(f"Name: {card.name}")
        print(f"Description: {card.description}")
        print(f"Skills: {len(card.skills)}")
        for s in card.skills:
            desc = (s.description or "")[:60]
            if len(s.description or "") > 60:
                desc += "..."
            print(f"  - {s.id}: {s.name} — {desc}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_a2a_call(url: str, task: str) -> int:
    """Send task to external A2A agent, stream output."""
    try:
        from hivemind.agents.a2a.client import A2AClient
        from hivemind.agents.a2a.types import A2ATaskRequest
        import asyncio
        import uuid
        client = A2AClient()
        request = A2ATaskRequest(id=str(uuid.uuid4()), message={"text": task}, session_id=None)
        async def _stream():
            async for chunk in client.stream_task(url, request):
                print(chunk, end="", flush=True)
        asyncio.run(_stream())
        print()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_start(args) -> int:
    """Start a node in the foreground (controller, worker, or hybrid)."""
    try:
        role = getattr(args, "role", "hybrid")
        port = getattr(args, "port", None)
        workers = getattr(args, "workers", None)
        tags = getattr(args, "tags", "") or ""
        print(f"Node role: {role}, port: {port or 'config default'}, workers: {workers or 'config default'}", file=sys.stderr)
        if tags:
            print(f"Tags: {[t.strip() for t in tags.split(',') if t.strip()]}", file=sys.stderr)
        print("Distributed node start: set nodes.mode=distributed and nodes.role in hivemind.toml, then run your process.", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_status(args) -> int:
    """Query controller GET /status."""
    url = getattr(args, "controller_url", None)
    if not url:
        try:
            from hivemind.config import get_config
            url = get_config().nodes.controller_url
        except Exception:
            url = "http://localhost:7700"
    try:
        import httpx
        r = httpx.get(f"{url.rstrip('/')}/status", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        from rich.console import Console
        from rich.table import Table
        cons = Console()
        cons.print("[bold]Run[/bold]", data.get("run_id", ""), "[bold]Leader[/bold]", data.get("node_id", ""))
        s = data.get("scheduler", {})
        cons.print("Tasks:", s.get("completed", 0), "completed,", s.get("pending", 0), "pending")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_workers(args) -> int:
    """List workers from controller GET /status."""
    url = getattr(args, "controller_url", None)
    if not url:
        try:
            from hivemind.config import get_config
            url = get_config().nodes.controller_url
        except Exception:
            url = "http://localhost:7700"
    try:
        import httpx
        r = httpx.get(f"{url.rstrip('/')}/status", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        for w in data.get("workers", []):
            print(w.get("node_id", "")[:8], w.get("host", ""), w.get("rpc_url", ""))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_drain(args) -> int:
    """POST /control drain target node."""
    url = getattr(args, "controller_url", None)
    try:
        from hivemind.config import get_config
        url = url or get_config().nodes.controller_url
    except Exception:
        url = "http://localhost:7700"
    try:
        import httpx
        r = httpx.post(
            f"{url.rstrip('/')}/control",
            json={"command": "drain", "target": getattr(args, "node_id", "")},
            timeout=10.0,
        )
        r.raise_for_status()
        print("Drain sent.", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_logs(args) -> int:
    """Stream GET /stream/events."""
    url = getattr(args, "controller_url", None) or "http://localhost:7700"
    try:
        from hivemind.config import get_config
        url = get_config().nodes.controller_url
    except Exception:
        pass
    print("Connect to", url, "stream/events (--follow); not implemented", file=sys.stderr)
    return 0


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


def _run_cache(subcommand: str, threshold: float | None = None) -> int:
    """Cache subcommand: stats | clear | tune."""
    from hivemind.cache import TaskCache
    from pathlib import Path

    db_path = Path(".hivemind") / "task_cache.db"
    cache = TaskCache()
    if subcommand == "stats":
        st = cache.stats()
        print(f"Cached task results (exact): {st['entries']}")
        try:
            from hivemind.cache.store import get_default_cache_store
            store = get_default_cache_store(db_path)
            sst = store.stats()
            semantic_count = sst.get("semantic_entries", 0)
            if semantic_count > 0:
                try:
                    from hivemind.config import get_config
                    cfg = get_config()
                    th = getattr(getattr(cfg, "cache", None), "similarity_threshold", 0.92)
                except Exception:
                    th = 0.92
                print(f"Semantic cache: enabled (threshold: {th})")
                print(f"Cache entries: {st['entries'] + semantic_count} tasks")
                print("Hit rate: N/A (run with semantic cache to collect)")
                print("Avg similarity: N/A")
                print("Est. tokens saved: N/A")
            else:
                print("Semantic cache: disabled or empty")
        except Exception:
            pass
        return 0
    if subcommand == "clear":
        cache.clear()
        try:
            from hivemind.cache.store import get_default_cache_store
            get_default_cache_store(db_path).clear()
        except Exception:
            pass
        print("Cache cleared.")
        return 0
    if subcommand == "tune":
        try:
            from hivemind.cache.task_cache import SemanticTaskCache
            from hivemind.cache.embedding_index import _cosine_sim, bytes_to_embedding
            sem = SemanticTaskCache(
                similarity_threshold=threshold or 0.92,
                max_age_hours=168.0,
            )
            entries = sem.store.list_semantic_entries()
            if len(entries) < 2:
                print("Need at least 2 semantic cache entries to tune.")
                return 0
            # Use last 50
            entries = entries[-50:]
            # Load embeddings
            vecs = [bytes_to_embedding(e[0]) for e in entries]
            ths = [0.85, 0.88, 0.90, 0.92, 0.95]
            print("Threshold | Entries that would match self | Avg other-match count")
            print("----------|-------------------------------|----------------------")
            for th in ths:
                self_ok = sum(1 for i in range(len(vecs)) if _cosine_sim(vecs[i], vecs[i]) >= th)
                other_count = 0
                for i in range(len(vecs)):
                    for j in range(len(vecs)):
                        if i != j and _cosine_sim(vecs[i], vecs[j]) >= th:
                            other_count += 1
                avg_other = other_count / len(vecs) if vecs else 0
                print(f"  {th:.2f}     | {self_ok}/{len(vecs)}                          | {avg_other:.1f}")
            return 0
        except Exception as e:
            print(f"Cache tune failed: {e}", file=sys.stderr)
            return 1
    print("Usage: hivemind cache stats | hivemind cache clear | hivemind cache tune [--threshold 0.90]", file=sys.stderr)
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


def _run_synthesize(
    query: str,
    no_kg: bool = False,
    json_out: bool = False,
    since: str | None = None,
) -> int:
    """Cross-run synthesis: answer query using all memory and optional KG."""
    import json
    from datetime import datetime, timezone
    from rich.console import Console
    from rich.panel import Panel
    from hivemind.config import get_config
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex
    from hivemind.knowledge.knowledge_graph import KnowledgeGraph
    from hivemind.intelligence.synthesis import CrossRunSynthesizer
    from hivemind.utils.models import resolve_model
    from hivemind.providers.model_router import TaskType

    cfg = get_config()
    store = get_default_store()
    index = MemoryIndex(store=store)
    worker_model = resolve_model(cfg.models.worker, TaskType.ANALYSIS)
    kg = None if no_kg else KnowledgeGraph(store=store)
    if kg and not no_kg:
        kg.load()
        kg.build_from_memory(merge=True)
    synthesizer = CrossRunSynthesizer(memory_index=index, knowledge_graph=kg, worker_model=worker_model)
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            pass
    out_chunks = []
    console = Console()
    if json_out:
        full = synthesizer.synthesize(query, max_sources=20, stream=False, use_kg=not no_kg, since=since_dt)
        answer = full if isinstance(full, str) else "".join(full)
        memories = index.query_across_runs(query, top_k=20, include_archived=False)
        if since_dt:
            memories = [m for m in memories if m.timestamp >= since_dt]
        run_ids = list(dict.fromkeys(getattr(m, "run_id", "") or "" for m in memories))
        run_ids = [r for r in run_ids if r]
        obj = {"query": query, "sources_used": len(memories), "run_ids": run_ids, "answer": answer}
        print(json.dumps(obj, indent=2))
        return 0
    with console.status("Synthesizing..."):
        it = synthesizer.synthesize(query, max_sources=20, stream=True, use_kg=not no_kg, since=since_dt)
        for chunk in it:
            out_chunks.append(chunk)
            console.print(chunk, end="")
    console.print()
    memories = index.query_across_runs(query, top_k=20, include_archived=False)
    if since_dt:
        memories = [m for m in memories if m.timestamp >= since_dt]
    run_ids = list(dict.fromkeys(getattr(m, "run_id", "") or "" for m in memories))
    run_ids = [r for r in run_ids if r]
    console.print(Panel(f"Sources: {len(memories)} records across {len(run_ids)} runs\nRun IDs: {', '.join(run_ids[:15])}{'...' if len(run_ids) > 15 else ''}", title="Sources"))
    return 0


def _run_memory_consolidate(dry_run: bool = False, min_cluster_size: int = 3) -> int:
    """Consolidate similar memory records: cluster, summarize, archive."""
    import asyncio
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn
    from hivemind.config import get_config
    from hivemind.memory.memory_store import get_default_store
    from hivemind.memory.memory_index import MemoryIndex
    from hivemind.memory.consolidation import MemoryConsolidator
    from hivemind.utils.models import resolve_model
    from hivemind.providers.model_router import TaskType

    store = get_default_store()
    index = MemoryIndex(store=store)
    cfg = get_config()
    worker_model = resolve_model(cfg.models.worker, TaskType.ANALYSIS)
    consolidator = MemoryConsolidator(min_cluster_size=min_cluster_size)
    records = store.list_memory(limit=5000, include_archived=False)
    console = Console()
    console.print(f"Scanning {len(records)} memory records...")
    try:
        report = asyncio.get_event_loop().run_until_complete(
            consolidator.consolidate(store, index, worker_model, dry_run=dry_run)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        report = loop.run_until_complete(
            consolidator.consolidate(store, index, worker_model, dry_run=dry_run)
        )
    avg_per = report.records_archived / report.clusters_consolidated if report.clusters_consolidated else 0
    console.print(f"Found {report.clusters_found} clusters (avg {avg_per:.1f} records/cluster)")
    console.print(f"Consolidating {report.clusters_consolidated} clusters with {min_cluster_size}+ records...")
    with Progress(SpinnerColumn(), console=console) as progress:
        progress.add_task("consolidate", total=report.clusters_consolidated)
    console.print("Results:")
    console.print(f"  Records archived:   {report.records_archived}")
    console.print(f"  Summaries created:   {report.records_created}")
    console.print(f"  Est. tokens saved:   ~{report.tokens_saved_estimate} per run")
    if dry_run:
        console.print("Run hivemind memory consolidate without --dry-run to apply changes.")
    return 0


def _run_checkpoint_dispatch(args: object) -> int:
    if getattr(args, "checkpoint_cmd", None) == "restore":
        return _run_checkpoint_restore(getattr(args, "run_id", ""))
    return _run_checkpoint_list(args)


def _run_checkpoint_list(args: object) -> int:
    """List all checkpoint files with run_id, task counts, timestamp."""
    from hivemind.config import get_config
    from hivemind.swarm.checkpointer import SchedulerCheckpointer
    import os
    try:
        cfg = get_config()
        events_dir = getattr(cfg, "events_dir", ".hivemind/events") or ".hivemind/events"
    except Exception:
        events_dir = ".hivemind/events"
    ckp = SchedulerCheckpointer(events_dir=events_dir)
    if not os.path.isdir(events_dir):
        print("No checkpoint directory found.")
        return 0
    found = []
    for name in os.listdir(events_dir):
        if name.endswith(".checkpoint.json"):
            run_id = name.replace(".checkpoint.json", "")
            path = os.path.join(events_dir, name)
            try:
                import json
                with open(path, "r") as f:
                    data = json.load(f)
                completed = data.get("completed_count", 0)
                failed = data.get("failed_count", 0)
                snapshot_at = data.get("snapshot_at", "")[:19]
                found.append((run_id, completed, failed, snapshot_at))
            except Exception:
                found.append((run_id, "?", "?", ""))
    if not found:
        print("No checkpoint files found.")
        return 0
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="Checkpoints")
        table.add_column("Run ID", style="dim")
        table.add_column("Completed", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Snapshot at")
        for run_id, completed, failed, snapshot_at in sorted(found, key=lambda x: -len(x[0])):
            table.add_row(run_id[:48], str(completed), str(failed), snapshot_at)
        console.print(table)
    except ImportError:
        for run_id, completed, failed, snapshot_at in found:
            print(f"{run_id}  completed={completed}  failed={failed}  {snapshot_at}")
    return 0


def _run_checkpoint_restore(run_id: str) -> int:
    """Restore a run from checkpoint and resume execution."""
    from hivemind.config import get_config
    from hivemind.swarm.checkpointer import SchedulerCheckpointer
    from hivemind.types.exceptions import CheckpointNotFoundError
    if not run_id or not run_id.strip():
        print("Error: run_id required. Use: hivemind checkpoint restore <run_id>", file=sys.stderr)
        return 1
    run_id = run_id.strip()
    try:
        cfg = get_config()
        events_dir = getattr(cfg, "events_dir", ".hivemind/events") or ".hivemind/events"
    except Exception:
        events_dir = ".hivemind/events"
    ckp = SchedulerCheckpointer(events_dir=events_dir)
    try:
        scheduler = ckp.restore_or_raise(run_id)
    except CheckpointNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Restored scheduler for run_id={run_id!r}: {len(scheduler.get_all_tasks())} tasks, {scheduler.get_results()} results.")
    print("Resume execution is not yet implemented (1.10). Use checkpoint list to inspect state.")
    return 0


def _run_audit_dispatch(args: object) -> int:
    """Audit: print table, export, or verify."""
    from hivemind.config import get_config
    from hivemind.audit.logger import AuditLogger
    cmd = getattr(args, "audit_cmd", None)
    run_id = getattr(args, "run_id", None)
    export_fmt = getattr(args, "export", None)
    if cmd == "verify":
        run_id = getattr(args, "run_id", run_id)
        if not run_id:
            print("Error: run_id required for verify", file=sys.stderr)
            return 1
        cfg = get_config()
        ok, msg = AuditLogger.verify(run_id, cfg.data_dir)
        print(msg)
        return 0 if ok else 1
    if not run_id:
        print("Error: run_id required (e.g. hivemind audit events_2025-03-10...)", file=sys.stderr)
        return 1
    cfg = get_config()
    logger = AuditLogger(cfg.data_dir, run_id=run_id)
    if export_fmt:
        out = logger.export(run_id, format=export_fmt)
        print(out)
        return 0
    out = logger.export(run_id, format="jsonl")
    if not out:
        print(f"No audit log for run_id={run_id}", file=sys.stderr)
        return 1
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title=f"Audit log: {run_id}")
        table.add_column("timestamp")
        table.add_column("event_type")
        table.add_column("task_id")
        table.add_column("resource")
        table.add_column("success")
        for line in out.strip().split("\n"):
            if not line:
                continue
            import json
            r = json.loads(line)
            table.add_row(
                r.get("timestamp", "")[:19],
                r.get("event_type", ""),
                r.get("task_id", ""),
                r.get("resource", ""),
                str(r.get("success", "")),
            )
        console.print(table)
    except Exception:
        print(out)
    return 0


def _run_explain(args: object) -> int:
    """Explain: decision records for run or task."""
    run_id = getattr(args, "run_id", None)
    task_id = getattr(args, "task_id", None)
    if not run_id:
        print("Error: run_id required", file=sys.stderr)
        return 1
    try:
        from hivemind.explainability.decision_tree import DecisionTreeBuilder
        from hivemind.config import get_config
        cfg = get_config()
        events_dir = cfg.events_dir
        builder = DecisionTreeBuilder()
        records = builder.build_from_events(run_id, events_dir)
        if not records:
            print(f"No decision records for run_id={run_id}", file=sys.stderr)
            return 1
        if task_id:
            records = [r for r in records if r.task_id == task_id]
            if not records:
                print(f"No task {task_id} in run {run_id}", file=sys.stderr)
                return 1
        for r in records:
            print(f"--- {r.task_id} ---")
            print(f"  strategy: {r.strategy_selected}")
            print(f"  model: {r.model_selected} ({r.model_tier})")
            print(f"  tools: {r.tools_selected}")
            print(f"  confidence: {r.confidence:.0%}")
            print(f"  rationale: {r.rationale[:300]}..." if len(r.rationale or "") > 300 else f"  rationale: {r.rationale}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_simulate(args: object) -> int:
    """Simulate: dry-run planning, no LLM or tools."""
    import asyncio
    task = getattr(args, "task", "")
    cost_only = getattr(args, "cost_only", False) or getattr(args, "cost", False)
    if not task:
        print("Error: task required (e.g. hivemind simulate \"Summarize X\")", file=sys.stderr)
        return 1
    try:
        from hivemind.explainability.simulation import SimulationMode
        sim = SimulationMode()
        report = asyncio.run(sim.simulate(task))
        if cost_only:
            print(f"Estimated cost: {getattr(report, 'estimated_cost', 'N/A')}")
            return 0
        print(f"Tasks: {len(report.task_list)}")
        for t in report.task_list:
            print(f"  - {t}")
        print(f"Estimated cost: {getattr(report, 'estimated_cost', 'N/A')}")
        print(f"Estimated duration: {getattr(report, 'estimated_duration', 'N/A')}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_health(args: object) -> int:
    """Run health checks. Exit 0 if healthy, 1 otherwise. Print ✓/✗ per check."""
    import asyncio
    from hivemind.config import get_config
    from hivemind.runtime.health import HealthChecker, HealthReport
    try:
        cfg = get_config()
    except Exception:
        cfg = None
    if cfg is None:
        print("No config loaded; using defaults for health checks.")
        from hivemind.config.schema import HivemindConfigModel
        cfg = HivemindConfigModel()
    checker = HealthChecker()
    try:
        report = asyncio.run(checker.check(cfg))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        report = loop.run_until_complete(checker.check(cfg))
    try:
        from rich.console import Console
        console = Console()
        for name, ok in report.checks.items():
            if ok:
                console.print(f"  [green]✓[/green] {name}")
            else:
                console.print(f"  [red]✗[/red] {name}  {report.errors.get(name, '')}")
        if report.healthy:
            console.print("[green]healthy[/green]")
        else:
            console.print("[red]unhealthy[/red]")
    except ImportError:
        for name, ok in report.checks.items():
            sym = "✓" if ok else "✗"
            print(f"  {sym} {name}" + (f"  {report.errors.get(name, '')}" if not ok else ""))
        print("healthy" if report.healthy else "unhealthy")
    return 0 if report.healthy else 1


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
        help="Analyze a swarm run or repository",
        description="With a run_id: build run report and optional LLM analysis. With a path: repository analysis.",
        epilog="""
Examples:
  hivemind analyze events_2025-03-09...     # run analysis
  hivemind analyze events_xxx --no-ai --json
  hivemind analyze .                        # repo analysis
  hivemind analyze /path/to/repo
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analyze_parser.add_argument(
        "run_id_or_path",
        nargs="?",
        default=None,
        help="Run ID (e.g. events_...) for run analysis, or path (e.g. .) for repo analysis",
    )
    analyze_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip LLM analysis (run analysis only)",
    )
    analyze_parser.add_argument(
        "--json",
        action="store_true",
        dest="analyze_json",
        help="Output RunReport as JSON (run analysis only)",
    )
    analyze_parser.set_defaults(func=_run_analyze_dispatch)

    run_analyze_parser = subparsers.add_parser(
        "run-analyze",
        help="Analyze a swarm run by run_id",
        description="Build run report from event log, optional LLM analysis.",
        epilog="""
Examples:
  hivemind run-analyze events_2025-03-09...
  hivemind run-analyze events_2025-03-09... --no-ai
  hivemind run-analyze events_2025-03-09... --json
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_analyze_parser.add_argument("run_id", help="Run ID (e.g. from hivemind runs)")
    run_analyze_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip LLM analysis (stats only, no API call)",
    )
    run_analyze_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw RunReport as JSON",
    )
    run_analyze_parser.set_defaults(
        func=lambda a: _run_analyze_run(a.run_id, a.no_ai, a.json_output)
    )

    runs_parser = subparsers.add_parser(
        "runs",
        help="List run history or show run summary",
        description="List recent runs (or filter by --failed). With run_id: same as run-analyze <run_id> --no-ai.",
        epilog="""
Examples:
  hivemind runs
  hivemind runs --limit 10 --failed
  hivemind runs --json
  hivemind runs events_2025-03-09...
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    runs_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="If given: show report for this run (no AI, same as run-analyze <run_id> --no-ai)",
    )
    runs_parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=20,
        help="Max runs to list (default 20)",
    )
    runs_parser.add_argument(
        "--failed",
        action="store_true",
        help="Only list runs with failed_tasks > 0",
    )
    runs_parser.add_argument(
        "--json",
        action="store_true",
        dest="runs_json",
        help="Output runs list as JSON",
    )
    runs_parser.set_defaults(func=_run_runs)

    memory_parser = subparsers.add_parser(
        "memory",
        help="List memory or consolidate",
        description="List stored memory entries or consolidate similar records.",
        epilog="""
Examples:
  hivemind memory
  hivemind memory -n 50
  hivemind memory consolidate [--dry-run] [--min-cluster-size 3]
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    memory_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Max entries to show (for list)"
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_cmd", help="memory subcommand")
    memory_list_p = memory_sub.add_parser("list", help="List memory entries (default)")
    memory_list_p.add_argument("--limit", "-n", type=int, default=20, help="Max entries")
    memory_list_p.set_defaults(func=lambda a: _run_memory(getattr(a, "limit", 20)))
    memory_parser.set_defaults(memory_cmd="list", func=lambda a: _run_memory(getattr(a, "limit", 20)))
    memory_consolidate_p = memory_sub.add_parser("consolidate", help="Cluster and summarize similar memories")
    memory_consolidate_p.add_argument("--dry-run", action="store_true", help="Preview without writing")
    memory_consolidate_p.add_argument("--min-cluster-size", type=int, default=3, help="Min records per cluster (default 3)")
    memory_consolidate_p.set_defaults(func=lambda a: _run_memory_consolidate(getattr(a, "dry_run", False), getattr(a, "min_cluster_size", 3)))

    synthesize_parser = subparsers.add_parser(
        "synthesize",
        help="Cross-run synthesis",
        description="Answer a question using all memory (and optional knowledge graph) across runs.",
        epilog="""
Examples:
  hivemind synthesize "What have I learned about rate limiting in APIs?"
  hivemind synthesize "Summarize findings about transformer architectures" --no-kg
  hivemind synthesize "What datasets have I worked with?" --json
  hivemind synthesize "Recent findings" --since 2025-01-01
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    synthesize_parser.add_argument("query", help="Question to synthesize from memory")
    synthesize_parser.add_argument("--no-kg", action="store_true", help="Skip knowledge graph, use memory only")
    synthesize_parser.add_argument("--json", action="store_true", help="Output JSON: query, sources_used, run_ids, answer")
    synthesize_parser.add_argument("--since", metavar="DATE", help="Filter memory to records after date (ISO)")
    synthesize_parser.set_defaults(func=lambda a: _run_synthesize(a.query, a.no_kg, a.json, getattr(a, "since", None)))

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

    mcp_parser = subparsers.add_parser(
        "mcp",
        help="MCP server commands (list, test, add)",
        description="List configured MCP servers, test connection, or add a server interactively.",
    )
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_cmd", help="Subcommand")
    mcp_list_p = mcp_sub.add_parser("list", help="List MCP servers and tool counts")
    mcp_list_p.set_defaults(func=lambda a: _run_mcp_list())
    mcp_test_p = mcp_sub.add_parser("test", help="Test connection to an MCP server")
    mcp_test_p.add_argument("server_name", help="Server name from config")
    mcp_test_p.set_defaults(func=lambda a: _run_mcp_test(a.server_name))
    mcp_add_p = mcp_sub.add_parser("add", help="Interactively add an MCP server to hivemind.toml")
    mcp_add_p.set_defaults(func=lambda a: _run_mcp_add())
    mcp_parser.set_defaults(mcp_cmd="list", func=lambda a: _run_mcp_list())

    a2a_parser = subparsers.add_parser(
        "a2a",
        help="A2A agent commands (serve, discover, call)",
        description="Run A2A server, discover external agents, or call an agent with a task.",
    )
    a2a_sub = a2a_parser.add_subparsers(dest="a2a_cmd", help="Subcommand")
    a2a_serve_p = a2a_sub.add_parser("serve", help="Start A2A server")
    a2a_serve_p.add_argument("--port", type=int, default=None, help="Port (default: config or 8080)")
    a2a_serve_p.set_defaults(func=lambda a: _run_a2a_serve(getattr(a, "port", None)))
    a2a_discover_p = a2a_sub.add_parser("discover", help="Fetch AgentCard from URL, print skills")
    a2a_discover_p.add_argument("url", help="Agent URL (e.g. http://localhost:8080)")
    a2a_discover_p.set_defaults(func=lambda a: _run_a2a_discover(a.url))
    a2a_call_p = a2a_sub.add_parser("call", help="Send task to external A2A agent, stream output")
    a2a_call_p.add_argument("url", help="Agent URL")
    a2a_call_p.add_argument("task", help="Task text to send")
    a2a_call_p.set_defaults(func=lambda a: _run_a2a_call(a.url, a.task))
    a2a_parser.set_defaults(a2a_cmd=None, func=lambda a: a2a_parser.print_help() or 0)

    node_parser = subparsers.add_parser(
        "node",
        help="Distributed node commands (v1.10)",
        description="Start a node, query status, drain workers, stream events.",
    )
    node_sub = node_parser.add_subparsers(dest="node_cmd", help="Subcommand")
    node_start_p = node_sub.add_parser("start", help="Start a node in the foreground")
    node_start_p.add_argument("--role", choices=["controller", "worker", "hybrid"], default="hybrid", help="Node role")
    node_start_p.add_argument("--port", type=int, default=None, help="RPC port")
    node_start_p.add_argument("--workers", type=int, default=None, help="Max workers (worker node)")
    node_start_p.add_argument("--tags", type=str, default="", help="Comma-separated tags e.g. gpu,high-mem")
    node_start_p.set_defaults(func=lambda a: _run_node_start(a))
    node_status_p = node_sub.add_parser("status", help="Query controller status")
    node_status_p.add_argument("--controller-url", type=str, default=None, help="Controller RPC URL")
    node_status_p.set_defaults(func=lambda a: _run_node_status(a))
    node_workers_p = node_sub.add_parser("workers", help="List workers from controller")
    node_workers_p.add_argument("--controller-url", type=str, default=None)
    node_workers_p.set_defaults(func=lambda a: _run_node_workers(a))
    node_drain_p = node_sub.add_parser("drain", help="Drain a worker (stop new tasks)")
    node_drain_p.add_argument("node_id", help="Worker node ID")
    node_drain_p.add_argument("--controller-url", type=str, default=None)
    node_drain_p.set_defaults(func=lambda a: _run_node_drain(a))
    node_logs_p = node_sub.add_parser("logs", help="Stream events from controller")
    node_logs_p.add_argument("--follow", action="store_true", help="Keep connection open")
    node_logs_p.add_argument("--controller-url", type=str, default=None)
    node_logs_p.set_defaults(func=lambda a: _run_node_logs(a))

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
  hivemind cache tune [--threshold 0.90]
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cache_parser.add_argument(
        "subcommand",
        nargs="?",
        default="stats",
        choices=["stats", "clear", "tune"],
        help="stats | clear | tune",
    )
    cache_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Similarity threshold for tune (e.g. 0.90)",
    )
    cache_parser.set_defaults(func=lambda a: _run_cache(a.subcommand, getattr(a, "threshold", None)))

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
  hivemind credentials set azure endpoint \"https://.../openai/v1\"
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
    credentials_parser.add_argument(
        "value",
        nargs="?",
        help="Value (for set only). Omit to be prompted, or pipe: echo 'val' | hivemind credentials set azure endpoint",
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

    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="List checkpoints or restore a run",
        description="List checkpoint files or restore a run from checkpoint and resume.",
    )
    checkpoint_sub = checkpoint_parser.add_subparsers(dest="checkpoint_cmd", help="Subcommand")
    checkpoint_list_p = checkpoint_sub.add_parser("list", help="List all checkpoint files")
    checkpoint_list_p.set_defaults(func=_run_checkpoint_dispatch)
    checkpoint_restore_p = checkpoint_sub.add_parser("restore", help="Restore run from checkpoint")
    checkpoint_restore_p.add_argument("run_id", help="Run ID to restore")
    checkpoint_restore_p.set_defaults(func=_run_checkpoint_dispatch)
    checkpoint_parser.set_defaults(checkpoint_cmd="list", func=_run_checkpoint_dispatch)

    audit_parser = subparsers.add_parser(
        "audit",
        help="View or export audit log for a run",
        description="Print audit log as table, export to CSV/JSONL, or verify chain integrity.",
    )
    audit_parser.add_argument("run_id", nargs="?", default=None, help="Run ID (e.g. events_...)")
    audit_parser.add_argument("--export", choices=["jsonl", "csv", "siem"], default=None, help="Export format")
    audit_sub = audit_parser.add_subparsers(dest="audit_cmd", help="Subcommand")
    audit_verify_p = audit_sub.add_parser("verify", help="Verify audit log chain integrity")
    audit_verify_p.add_argument("run_id", help="Run ID to verify")
    audit_verify_p.set_defaults(audit_cmd="verify")
    audit_parser.set_defaults(func=_run_audit_dispatch)

    explain_parser = subparsers.add_parser(
        "explain",
        help="Show decision records for a run or task",
        description="Print decision tree and rationale for agent actions.",
    )
    explain_parser.add_argument("run_id", help="Run ID")
    explain_parser.add_argument("task_id", nargs="?", default=None, help="Optional task ID for single task")
    explain_parser.set_defaults(func=_run_explain)

    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Dry-run planning without LLM or tool execution",
        description="Run planner and scheduler only; output task list and cost estimate.",
    )
    simulate_parser.add_argument("task", help="Root task description")
    simulate_parser.add_argument("--cost", action="store_true", help="Print cost estimate only")
    simulate_parser.set_defaults(func=_run_simulate)

    health_parser = subparsers.add_parser(
        "health",
        help="Health and readiness check",
        description="Run health checks (bus, memory, tools, KG, checkpoint dir). Exit 0 if healthy, 1 otherwise.",
    )
    health_parser.set_defaults(func=_run_health)

    _load_project_dotenv()
    args = parser.parse_args()
    if not args.command:
        return _run_tui()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
