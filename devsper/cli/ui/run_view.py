"""
Live run view: real-time task table, tool activity, cost during devsper run.
Polls event log (or subscribes to bus when available). Rich Live, refresh 10 Hz.
"""

# ROOT CAUSE DIAGNOSIS (evidence-based; see call sites below)
# Q1: Live() instantiations per distributed controller run:
#   - runtime/devsper/cli/ui/controller_run_view.py:128 (ControllerRunView.run)
#   - runtime/devsper/cli/ui/run_view.py:451 (run_live_view)
#   In distributed runs, controller.py starts ControllerRunView; run_view.run_live_view is not used.
#   Fix: ensure the distributed path constructs exactly one Live for the run lifetime.
#
# Q2: Console() instances during a run:
#   - runtime/devsper/cli/ui/theme.py created both console + err_console (two instances).
#   Fix: make err_console alias console so there is exactly one shared Console.
#
# Q3: Live screen mode:
#   - Both Live call sites omit screen=..., so Rich defaults apply (inline; screen=False).
#   Fix: set screen=False explicitly and transient=False to keep final panel visible.
#
# Q4: Controller/executor callbacks into TUI:
#   - ControllerRunView only polls event log; worker heartbeats / task claims/completions are not emitted to that log.
#   Fix: ControllerNode must call into the active run view on worker/task state changes.
#
# Q5: live.stop()/live.start() loops:
#   - runtime/devsper/cli/ui/controller_run_view.py stops/starts live for clarification prompts (legit),
#     but there must be no stop/start used as a "refresh" mechanism.
#   Fix: do not stop/start for updates; updates must be live.update(renderable).
#
# Q6: print()/console.print() during Live:
#   - runtime/examples/distributed/run_controller.py uses bare print() for progress/results (outside Rich),
#     which can interleave with Live output and create orphan lines/panels.
#   Fix: remove those print() calls; show progress inside the Live UI and print summary only after Live stops.

import logging
import os
import asyncio
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from devsper.cli.ui.theme import console, ThemeStyle
from devsper.cli.ui.components import devsperHeader, TaskRow, RoleTag, CostDisplay, SectionHeader


def is_interactive() -> bool:
    """True if we can show interactive prompts (TTY and not CI)."""
    return sys.stdout.isatty() and not os.environ.get("CI")


def _field_get(field: Any, key: str, default: Any = None) -> Any:
    if isinstance(field, dict):
        return field.get(key, default)
    return getattr(field, key, default)


class ClarificationWidget:
    """
    Pauses the live display and renders an interactive clarification prompt.
    Returns ClarificationResponse when user completes it.
    """

    def __init__(self, req: Any, theme: ThemeStyle) -> None:
        self.req = req
        self.theme = theme

    def render(self) -> Any:
        from devsper.events import ClarificationResponse

        if not is_interactive():
            answers = {}
            for field in self.req.fields:
                q = _field_get(field, "question")
                default = _field_get(field, "default")
                ftype = _field_get(field, "type", "text")
                if default is not None:
                    answers[q] = default
                elif ftype == "mcq":
                    opts = _field_get(field, "options") or []
                    if opts:
                        answers[q] = opts[0]
            return ClarificationResponse(
                request_id=self.req.request_id,
                answers=answers,
                skipped=True,
            )

        from rich.prompt import Prompt
        from rich.panel import Panel

        answers = {}
        console.print()
        console.print(
            Panel(
                f"[dim]{self.req.context}[/dim]",
                title=f"[bold {self.theme.amber}]"
                f"[{self.req.agent_role}] needs clarification[/]",
                border_style="dim",
                padding=(0, 2),
            )
        )
        console.print()

        for field in self.req.fields:
            answer = self._render_field(console, field)
            if answer is not None:
                q = _field_get(field, "question")
                if q:
                    answers[q] = answer

        console.print("  [hive.success]Answer received. Sending to worker...[/]")
        console.print()
        return ClarificationResponse(
            request_id=self.req.request_id,
            answers=answers,
            skipped=False,
        )

    def _render_field(self, console: Any, field: Any) -> Any:
        q = _field_get(field, "question")
        ftype = _field_get(field, "type", "text")

        if ftype == "mcq":
            return self._mcq(console, q, _field_get(field, "options") or [], _field_get(field, "default"))

        if ftype == "multi_select":
            return self._multi_select(console, q, _field_get(field, "options") or [])

        if ftype == "confirm":
            from rich.prompt import Prompt
            result = Prompt.ask(
                f"  [bold]{q}[/bold]",
                choices=["y", "n"],
                default=_field_get(field, "default") or "y",
                console=console,
            )
            return result == "y"

        if ftype == "rank":
            return self._rank(console, q, _field_get(field, "options") or [])

        # text
        if not _field_get(field, "required", True):
            console.print(f"  [bold]{q}[/bold] [dim](optional, Enter to skip)[/dim]")
        else:
            console.print(f"  [bold]{q}[/bold]")
        from rich.prompt import Prompt
        result = Prompt.ask("  ", default="", console=console)
        return result if result else None

    def _mcq(self, console: Any, question: str, options: list, default: Any = None) -> str:
        from rich.prompt import Prompt

        console.print(f"  [bold]{question}[/bold]")
        console.print()

        default_index = 1
        if isinstance(default, str):
            d = default.strip().upper()
            if len(d) == 1 and "A" <= d <= "Z":
                idx = ord(d) - 64
                if 1 <= idx <= len(options):
                    default_index = idx
            else:
                try:
                    idx2 = options.index(default)
                    default_index = idx2 + 1
                except ValueError:
                    pass

        for i, opt in enumerate(options, 1):
            style = "amber" if i == default_index else "dim"
            console.print(f"    [{style}]{i}[/]  {opt}")

        custom_idx = len(options) + 1
        console.print(f"    [dim]{custom_idx}[/]  Enter custom answer")
        console.print()

        alpha_choices = [chr(ord("A") + i - 1) for i in range(1, custom_idx + 1)]
        choices = [str(i) for i in range(1, custom_idx + 1)] + alpha_choices
        choice = Prompt.ask(
            "  Select option",
            choices=choices,
            default=str(default_index if options else custom_idx),
            console=console,
        )
        c = (choice or "").strip().upper()
        if len(c) == 1 and "A" <= c <= "Z":
            selected = ord(c) - ord("A") + 1
        else:
            selected = int(choice)
        if selected == custom_idx:
            custom = Prompt.ask("  Custom answer", default="", console=console).strip()
            return custom if custom else (options[default_index - 1] if options else "")

        idx = selected - 1
        if 0 <= idx < len(options):
            return options[idx]
        return options[default_index - 1] if options else ""

    def _multi_select(self, console: Any, question: str, options: list) -> list:
        from rich.prompt import Prompt
        console.print(f"  [bold]{question}[/bold]")
        console.print("  [dim]Space to toggle, Enter to confirm[/dim]")
        console.print()
        for i, opt in enumerate(options, 1):
            console.print(f"    {i}. {opt}")
        console.print()
        raw = Prompt.ask(
            "  Select (e.g. 1,3)",
            default="1",
            console=console,
        )
        selected = []
        for part in raw.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < len(options):
                    selected.append(options[idx])
            except ValueError:
                pass
        return selected

    def _rank(self, console: Any, question: str, options: list) -> list:
        from rich.prompt import Prompt
        console.print(f"  [bold]{question}[/bold]")
        console.print("  [dim]Enter numbers in priority order (e.g. 2,1,3)[/dim]")
        console.print()
        for i, opt in enumerate(options, 1):
            console.print(f"    {i}. {opt}")
        console.print()
        default_order = ",".join(str(i + 1) for i in range(len(options)))
        raw = Prompt.ask("  Order", default=default_order, console=console)
        ranked = []
        for part in raw.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < len(options):
                    ranked.append(options[idx])
            except ValueError:
                pass
        return ranked


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
            from devsper.types.event import Event
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
            total_cost_usd_accum: float = 0.0
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
                    c = payload.get("cost_usd") or payload.get("cost")
                    if c is not None and isinstance(c, (int, float)):
                        total_cost_usd_accum += float(c)
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
            # Run start from first event timestamp so duration summary is accurate
            if events:
                first = events[0]
                ts = getattr(first, "timestamp", None)
                if ts is not None and hasattr(ts, "timestamp"):
                    self.started_at = ts.timestamp()
            if total_cost_usd_accum > 0:
                self.total_cost_usd = total_cost_usd_accum


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
        import devsper
        version = getattr(devsper, "__version__", "")
    except Exception:
        pass
    elapsed = int(time.time() - state.started_at)
    time_str = f"{elapsed // 60}:{elapsed % 60:02d}"
    header_left = devsperHeader(version=version, workers=state.worker_count or 0)
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
    clarification_queue: queue.Queue | None = None,
    swarm: Any = None,
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
                    from devsper.types.event import Event
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

    theme_style = ThemeStyle()
    with Live(
        get_renderable(),
        refresh_per_second=10,
        console=console,
        screen=False,
        transient=False,
    ) as live:
        while not is_finished():
            if clarification_queue is not None and swarm is not None:
                executor = getattr(swarm, "_current_executor", None)
                if executor is not None:
                    try:
                        req = clarification_queue.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        widget = ClarificationWidget(req, theme_style)
                        response = widget.render()
                        executor.receive_clarification(response)
            time.sleep(poll_interval)
            live.update(get_renderable())
    state.finished = True
    state.update_from_events(log_path)
    return state


class DistributedRunView:
    """
    Async run view for distributed controller runs.

    - Exactly one Live instance per run lifetime (start once, stop once).
    - Exactly one refresh loop task calling live.update(self._build_layout()).
    - Event handlers update internal state; refresh loop renders from current state.
    """

    def __init__(
        self,
        *,
        log_path: str | None,
        run_id: str,
        poll_interval: float = 0.1,
        stop_check: Callable[[], bool],
        clarification_manager: Any | None = None,
    ) -> None:
        from rich.live import Live

        self.log_path = log_path
        self.stop_check = stop_check
        self.poll_interval = poll_interval
        self.theme = ThemeStyle()
        self.state = RunViewState(
            run_id=run_id,
            run_id_short=(run_id or "")[:8],
            planner_message="Selecting strategy...",
            planner_visible=True,
            worker_count=0,
        )
        self._live: Live | None = None
        self._refresh_task: asyncio.Task | None = None
        self._done = asyncio.Event()
        self._worker_ids: set[str] = set()
        self._task_status_overrides: dict[str, str] = {}
        self._manager: Any | None = None
        self._saved_log_level: int | None = None
        self._saved_controller_log_level: int | None = None  # suppress controller INFO during TUI
        if clarification_manager is not None:
            self.attach_clarification_manager(clarification_manager)

    def _build_layout(self) -> object:
        # Keep event-log polling for task/tool/cost display, but overlay live worker count.
        self.state.update_from_events(self.log_path)
        if self._task_status_overrides:
            with self.state._lock:
                for t in self.state.tasks:
                    ov = self._task_status_overrides.get(t.task_id)
                    if ov:
                        t.status = ov
        return _render_live_layout(self.state)

    async def start(self) -> None:
        from rich.live import Live

        if self._live is not None:
            return
        # Prevent TUI duplication and log flood: controller INFO (dispatch, restore, claim) would
        # interleave with clarification prompts and overwrite the TUI.
        root = logging.getLogger()
        self._saved_log_level = root.level
        root.setLevel(logging.WARNING)
        ctrl_log = logging.getLogger("devsper.nodes.controller")
        self._saved_controller_log_level = ctrl_log.level
        ctrl_log.setLevel(logging.WARNING)
        live = Live(
            self._build_layout(),
            console=console,
            refresh_per_second=10,
            screen=False,
            transient=False,
            vertical_overflow="crop",
        )
        live.start()
        self._live = live
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        self._done.set()
        if self._refresh_task is not None:
            try:
                await self._refresh_task
            except Exception:
                pass
            self._refresh_task = None
        if self._live is not None:
            try:
                self._live.update(self._build_layout())
            except Exception:
                pass
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None
        # Restore logging levels so progress/results can be logged after TUI
        if self._saved_log_level is not None:
            logging.getLogger().setLevel(self._saved_log_level)
            self._saved_log_level = None
        if self._saved_controller_log_level is not None:
            logging.getLogger("devsper.nodes.controller").setLevel(self._saved_controller_log_level)
            self._saved_controller_log_level = None

    async def _refresh_loop(self) -> None:
        # Single refresh loop for entire run lifetime.
        while not self._done.is_set():
            if self.stop_check():
                break
            if self._live is not None:
                try:
                    self._live.update(self._build_layout())
                except Exception:
                    pass
            await asyncio.sleep(self.poll_interval)
        # Final render
        if self._live is not None:
            try:
                self._live.update(self._build_layout())
            except Exception:
                pass

    def attach_clarification_manager(self, manager: Any) -> None:
        self._manager = manager
        try:
            manager.on_clarification_ready = self._handle_clarification_ready
            manager.on_queue_changed = self._on_queue_changed
        except Exception:
            pass

    def _on_queue_changed(self, snapshot: list[dict]) -> None:
        # Refresh will pick up any context changes from scheduler/event log.
        return

    async def _handle_clarification_ready(self, queued: Any) -> None:
        """
        Called by ClarificationManager when it's this request's turn.
        Must not return until user answers (or skips).
        Do not stop/start Live here: that would leave the old frame on screen and draw a new one
        below it, causing TUI duplication. Show the prompt below the Live area instead.
        """
        widget = ClarificationWidget(queued.request, self.theme)
        try:
            response = await asyncio.to_thread(widget.render)
            if self._manager is not None:
                self._manager.resolve(queued.request.request_id, response.answers)
        except KeyboardInterrupt:
            if self._manager is not None:
                self._manager.skip(queued.request.request_id)

    def on_worker_connected(self, node_id: str) -> None:
        if not node_id:
            return
        self._worker_ids.add(node_id)
        self.state.worker_count = len(self._worker_ids)
        self._live.update(self._build_layout()) if self._live is not None and getattr(self._live, "is_started", False) else None

    def on_worker_disconnected(self, node_id: str) -> None:
        if not node_id:
            return
        self._worker_ids.discard(node_id)
        self.state.worker_count = len(self._worker_ids)
        self._live.update(self._build_layout()) if self._live is not None and getattr(self._live, "is_started", False) else None

    def on_task_status_changed(self, task_id: str, status: str, node_id: str | None = None) -> None:
        # Best-effort overlay: if task exists in current state, update status immediately.
        # Otherwise event-log polling will populate it shortly.
        if not task_id:
            return
        if status:
            self._task_status_overrides[task_id] = status
        with self.state._lock:
            for t in self.state.tasks:
                if t.task_id == task_id:
                    t.status = status
                    break



def print_run_summary(state: RunViewState, results: dict[str, str], summary_only: bool = False) -> None:
    """Print final summary panel and optionally task results."""
    from rich.panel import Panel
    from rich.text import Text
    done = sum(1 for t in state.tasks if t.status == "completed")
    failed_n = sum(1 for t in state.tasks if t.status == "failed")
    skipped = sum(1 for t in state.tasks if t.status in ("skipped", "cached"))
    total = len(state.tasks)
    # Duration: started_at is set from first event in update_from_events when event log is read
    duration_s = time.time() - state.started_at
    if duration_s < 0:
        duration_s = 0.0
    cost_str = f"${state.total_cost_usd:.4f}" if (state.total_cost_usd is not None and state.total_cost_usd > 0) else "—"
    cache_hits = sum(1 for t in state.tasks if t.status == "cached")
    lines = [
        f"{total} tasks  ·  {done} completed  ·  {failed_n} failed  ·  {skipped} skipped",
        f"Duration: {duration_s:.1f}s  ·  Cost: {cost_str}  ·  Cache hits: {cache_hits}",
        f"run id: {state.run_id_short}",
    ]
    console.print(Panel("\n".join(lines), title="Run complete", border_style="hive.success"))
    if not summary_only and results:
        for task_id, result in results.items():
            console.print(
                Panel(
                    (result or "")[:2000] + ("..." if (result or "") and len(result) > 2000 else ""),
                    title=f"[dim]{(task_id or '')[:8]}[/dim]",
                    border_style="dim",
                    padding=(1, 2),
                )
            )
