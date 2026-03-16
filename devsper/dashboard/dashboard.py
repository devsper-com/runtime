"""
Minimal visualization: task DAG, swarm replay, memory entries, telemetry.

Uses Rich for terminal output when available; falls back to plain text.
"""

import os
from pathlib import Path

from devsper.swarm.scheduler import Scheduler
from devsper.runtime.visualize import visualize_scheduler_dag
from devsper.runtime.replay import replay_execution
from devsper.runtime.telemetry import collect_telemetry, print_telemetry_summary
from devsper.memory.memory_store import MemoryStore, get_default_store


def _latest_log_path(events_folder: str = ".devsper/events") -> str | None:
    if not os.path.isdir(events_folder):
        return None
    files = list(Path(events_folder).glob("events_*.jsonl"))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0])


def show_dashboard(
    scheduler: Scheduler | None = None,
    log_path: str | None = None,
    memory_store: MemoryStore | None = None,
    events_folder: str = ".devsper/events",
    memory_limit: int = 20,
) -> str:
    """
    Print a combined dashboard: task DAG (if scheduler given), swarm replay and telemetry
    (if log_path or latest log in events_folder), and recent memory entries (if store given).
    Returns the full dashboard as a string.
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        use_rich = True
    except ImportError:
        use_rich = False

    lines: list[str] = []

    if scheduler is not None:
        dag = visualize_scheduler_dag(scheduler)
        lines.append("=== TASK DAG ===")
        lines.append(dag)
        lines.append("")

    if log_path is None:
        log_path = _latest_log_path(events_folder)
    if log_path and os.path.exists(log_path):
        lines.append("=== SWARM REPLAY ===")
        lines.append(replay_execution(log_path))
        lines.append("")
        lines.append("=== TELEMETRY ===")
        lines.append(print_telemetry_summary(log_path))
        lines.append("")
    else:
        lines.append("=== SWARM REPLAY / TELEMETRY ===")
        lines.append("(no event log found)")
        lines.append("")

    store = memory_store or get_default_store()
    lines.append("=== MEMORY (recent) ===")
    try:
        records = store.list_memory(limit=memory_limit)
        if not records:
            lines.append("(no memory entries)")
        else:
            for r in records:
                lines.append(f"  [{r.memory_type.value}] {r.id}: {r.content[:120]}{'...' if len(r.content) > 120 else ''}")
    except Exception as e:
        lines.append(f"(error listing memory: {e})")
    lines.append("")

    out = "\n".join(lines)
    if use_rich:
        console = Console()
        console.print(Panel(out, title="Swarm Dashboard", border_style="blue"))
    else:
        print(out)
    return out
