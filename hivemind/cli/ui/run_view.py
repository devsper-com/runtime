"""
Live run view: real-time task table, tool activity, cost during hivemind run.
Polls event log (or subscribes to bus when available). Rich Live, refresh 10 Hz.
"""

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from hivemind.cli.ui.theme import console
from hivemind.cli.ui.components import HivemindHeader, TaskRow, RoleTag, CostDisplay, SectionHeader


@dataclass
class TaskState:
    task_id: str
    short_id: str
    description: str
    role: str
    status: str  # pending, running, completed, failed, cached, skipped
    duration_ms: int | None = None


@dataclass
class RunViewState:
    run_id: str
    run_id_short: str
    planner_message: str
    planner_visible: bool
    tasks: list[TaskState] = field(default_factory=list)
    tool_counts: dict[str, int] = field(default_factory=dict)
    total_cost_usd: float | None = None
    worker_count: int = 0
    started_at: float = field(default_factory=time.time)
    finished: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update_from_events(self, log_path: str | None) -> None:
        if not log_path or not os.path.isfile(log_path):
            return
        events = []
        try:
            from hivemind.types.event import Event
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(Event.from_json(line))
                    except Exception:
                        try:
                            events.append(Event.model_validate_json(line))
                        except Exception:
                            continue
        except Exception:
            return
        if not events:
            return
        with self._lock:
            task_descriptions: dict[str, str] = {}
            task_roles: dict[str, str] = {}
            started: set[str] = set()
            completed: set[str] = set()
            failed: set[str] = set()
            cached: set[str] = set()
            task_duration_ms: dict[str, int] = {}
            tool_counts: dict[str, int] = {}
            planner_done = False
            executor_done = False
            for e in events:
                payload = e.payload or {}
                tid = (payload.get("task_id") or "").strip()
                ev = getattr(e.type, "value", str(e.type))
                if ev == "task_created" and tid:
                    task_descriptions[tid] = (payload.get("description") or "").strip()
                    task_roles[tid] = (payload.get("role") or "").strip()
                elif ev in ("task_started", "agent_started") and tid:
                    started.add(tid)
                elif ev == "task_completed" and tid:
                    completed.add(tid)
                    started.discard(tid)
                    dur = payload.get("duration_ms") or payload.get("duration_seconds")
                    if dur is not None:
                        task_duration_ms[tid] = int(dur) if isinstance(dur, (int, float)) else 0
                elif ev == "task_failed" and tid:
                    failed.add(tid)
                    started.discard(tid)
                elif ev in ("agent_finished") and tid and tid not in completed and tid not in failed:
                    completed.add(tid)
                    started.discard(tid)
                elif ev == "task_cache_hit" and tid:
                    cached.add(tid)
                    completed.add(tid)
                    started.discard(tid)
                elif ev == "tool_called":
                    name = (payload.get("tool") or payload.get("tool_name") or "tool").strip()
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                elif ev == "planner_finished":
                    planner_done = True
                elif ev == "executor_finished":
                    executor_done = True
            running_ids = started - completed - failed - cached
            all_ids = sorted(set(task_descriptions) | running_ids | completed | failed | cached)
            self.tasks = []
            for tid in all_ids:
                desc = task_descriptions.get(tid, "")
                role = task_roles.get(tid, "")
                short = tid[:8] if len(tid) >= 8 else tid
                if tid in cached:
                    status = "cached"
                elif tid in failed:
                    status = "failed"
                elif tid in completed:
                    status = "completed"
                elif tid in running_ids:
                    status = "running"
                else:
                    status = "pending"
                dur_ms = task_duration_ms.get(tid)
                duration_str = f"{dur_ms}ms" if dur_ms is not None else ("..." if status == "running" else "—")
                if dur_ms is not None and dur_ms >= 1000:
                    duration_str = f"{dur_ms/1000:.1f}s"
                self.tasks.append(TaskState(
                    task_id=tid,
                    short_id=short,
                    description=desc,
                    role=role,
                    status=status,
                    duration_ms=dur_ms,
                ))
            self.tool_counts = dict(sorted(tool_counts.items(), key=lambda x: -x[1])[:6])
            self.planner_visible = not planner_done and not self.tasks
            if planner_done and not self.tasks and all_ids:
                self.planner_visible = False
            if not self.planner_message or "Selecting" in self.planner_message:
                last = events[-1] if events else None
                if last:
                    ev_type = getattr(last.type, "value", str(last.type))
                    if ev_type == "swarm_started":
                        self.planner_message = "Selecting strategy..."
                    elif ev_type == "planner_started":
                        self.planner_message = "Decomposing task into subtasks..."
                    elif ev_type == "planner_finished":
                        self.planner_message = "Building execution DAG..."
                    else:
                        self.planner_message = "Querying knowledge graph..."


def _render_live_layout(state: RunViewState) -> object:
    """Build Rich renderable for current state."""
    from rich.table import Table
    from rich.text import Text
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.live import Group

    # Header
    version = ""
    try:
        import hivemind
        version = getattr(hivemind, "__version__", "")
    except Exception:
        pass
    elapsed = int(time.time() - state.started_at)
    time_str = f"{elapsed // 60}:{elapsed % 60:02d}"
    header_left = HivemindHeader(version=version, workers=state.worker_count or 0)
    header_right = Text(f"run: {state.run_id_short}  {time_str}", style="hive.muted")
    header = Columns([header_left, header_right], expand=True)
    header = Panel(header, border_style="hive.dim", padding=(0, 1))

    # Planning phase
    planning_line = Text()
    if state.planner_visible:
        planning_line = Text("◎  ", style="hive.primary") + Text(state.planner_message, style="dim")
    else:
        strategy = "research"  # could come from events
        n = len(state.tasks)
        planning_line = Text("    strategy: ", style="hive.muted") + Text(strategy, style="hive.planner") + Text(f"  ·  planning {n} subtasks", style="hive.muted")
    planning_panel = Panel(planning_line, border_style="hive.dim", padding=(0, 1))

    # Task table (max 12 rows) — one column per row with full task line
    task_table = Table(show_header=False, box=None, padding=(0, 1))
    task_table.add_column("task", width=80)
    running_first = sorted(state.tasks, key=lambda t: (
        0 if t.status == "running" else 1,
        1 if t.status == "pending" else 0,
        0 if t.status == "completed" else 1,
        0 if t.status == "failed" else 1,
        t.task_id,
    ))
    for t in running_first[:12]:
        dur_str = f"{t.duration_ms}ms" if t.duration_ms is not None else ("..." if t.status == "running" else "—")
        if t.duration_ms is not None and t.duration_ms >= 1000:
            dur_str = f"{t.duration_ms/1000:.1f}s"
        tr = TaskRow(t.short_id, t.description, t.role, dur_str, t.status)
        task_table.add_row(tr)
    if len(state.tasks) > 12:
        task_table.add_row(Text("+ " + str(len(state.tasks) - 12) + " more tasks", style="hive.muted"))
    tasks_panel = Panel(Group(SectionHeader("Tasks"), task_table), border_style="hive.dim", padding=(0, 1))

    # Tool strip
    tool_parts = [Text(f"  {name}  ×{c}", style="hive.tool") for name, c in list(state.tool_counts.items())[:6]]
    tool_line = Text("  ").join(tool_parts) if tool_parts else Text("  (no tools yet)", style="hive.dim")
    tools_panel = Panel(Group(SectionHeader("Tools"), tool_line), border_style="hive.dim", padding=(0, 1))

    # Status bar
    done = sum(1 for t in state.tasks if t.status == "completed")
    failed_n = sum(1 for t in state.tasks if t.status == "failed")
    running_n = sum(1 for t in state.tasks if t.status == "running")
    total = len(state.tasks)
    cost_str = CostDisplay(state.total_cost_usd)
    status_bar = Text()
    status_bar.append_text(cost_str)
    status_bar.append(Text("  ·  ", style="hive.muted"))
    status_bar.append(Text(f"{state.worker_count} workers", style="hive.muted"))
    status_bar.append(Text("  ·  ", style="hive.muted"))
    status_bar.append(Text(f"{running_n} running", style="white"))
    status_bar.append(Text("  ·  ", style="hive.muted"))
    status_bar.append(Text(f"{done} done / {total} total", style="white"))
    status_panel = Panel(status_bar, border_style="hive.dim", padding=(0, 1))

    return Group(header, planning_panel, tasks_panel, tools_panel, status_panel)


def run_live_view(
    log_path: str | None,
    run_id: str,
    worker_count: int,
    poll_interval: float = 0.1,
    stop_check: Callable[[], bool] | None = None,
) -> RunViewState:
    """Run the live view until stop_check() returns True (e.g. swarm thread finished). Returns final state."""
    from rich.live import Live
    state = RunViewState(
        run_id=run_id,
        run_id_short=(run_id or "")[:8],
        planner_message="Selecting strategy...",
        planner_visible=True,
        worker_count=worker_count,
    )
    state.update_from_events(log_path)

    def get_renderable() -> object:
        state.update_from_events(log_path)
        return _render_live_layout(state)

    def is_finished() -> bool:
        if stop_check is not None and stop_check():
            return True
        if not log_path or not os.path.isfile(log_path):
            return False
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines[-15:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    from hivemind.types.event import Event
                    ev = Event.from_json(line)
                except Exception:
                    try:
                        ev = Event.model_validate_json(line)
                    except Exception:
                        continue
                if getattr(ev.type, "value", "") == "swarm_finished":
                    return True
        except Exception:
            pass
        return False

    with Live(get_renderable(), refresh_per_second=10, console=console) as live:
        while not is_finished():
            time.sleep(poll_interval)
            live.update(get_renderable())
    state.finished = True
    state.update_from_events(log_path)
    return state


def print_run_summary(state: RunViewState, results: dict[str, str], summary_only: bool = False) -> None:
    """Print final summary panel and optionally task results."""
    from rich.panel import Panel
    from rich.text import Text
    done = sum(1 for t in state.tasks if t.status == "completed")
    failed_n = sum(1 for t in state.tasks if t.status == "failed")
    skipped = sum(1 for t in state.tasks if t.status in ("skipped", "cached"))
    total = len(state.tasks)
    duration_s = time.time() - state.started_at
    cost_str = f"${state.total_cost_usd:.4f}" if state.total_cost_usd is not None else "—"
    cache_hits = sum(1 for t in state.tasks if t.status == "cached")
    lines = [
        f"{total} tasks  ·  {done} completed  ·  {failed_n} failed  ·  {skipped} skipped",
        f"Duration: {duration_s:.1f}s  ·  Cost: {cost_str}  ·  Cache hits: {cache_hits}",
        f"run id: {state.run_id_short}",
    ]
    console.print(Panel("\n".join(lines), title="Run complete", border_style="hive.success"))
    if not summary_only and results:
        for task_id, result in results.items():
            console.print(Text(f"--- {task_id} ---", style="hive.primary"))
            console.print((result or "")[:2000])
            if (result or "") and len(result) > 2000:
                console.print("...")
