"""
Controller-side async Live view for distributed runs.

Renders the same task table as run_view.py plus a clarification queue panel,
and attaches to ControllerNode-owned ClarificationManager so only one prompt
is shown at a time (no input corruption).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

from devsper.cli.ui.theme import console, ThemeStyle
from devsper.cli.ui.run_view import RunViewState, _render_live_layout, ClarificationWidget


def _render_clarification_queue_panel(manager: Any) -> Panel | None:
    try:
        count = int(manager.pending_count())
        snapshot = list(manager.queue_snapshot())
    except Exception:
        return None
    if count <= 0:
        return None
    active = next((s for s in snapshot if s.get("status") == "active"), None)
    queued = [s for s in snapshot if s.get("status") == "queued"]
    lines: list[str] = []
    if active:
        lines.append(
            f"[bold hive.primary]⏸  [{active.get('role','agent')}][/bold hive.primary] "
            f"[dim]on {active.get('node_id','?')}[/dim]  waiting for your input"
        )
    if queued:
        roles = ", ".join((q.get("role") or "agent") for q in queued[:3])
        more = f" +{len(queued)-3}" if len(queued) > 3 else ""
        lines.append(f"[dim]  {len(queued)} queued: {roles}{more}[/dim]")
    return Panel("\n".join(lines), border_style="hive.dim", padding=(0, 1))


class ControllerRunView:
    def __init__(
        self,
        *,
        log_path: str | None,
        run_id: str,
        worker_count: int,
        stop_check: Callable[[], bool],
        clarification_manager: Any | None = None,
        poll_interval: float = 0.1,
    ) -> None:
        self.log_path = log_path
        self.run_id = run_id
        self.worker_count = worker_count
        self.stop_check = stop_check
        self.poll_interval = poll_interval
        self.theme = ThemeStyle()
        self.state = RunViewState(
            run_id=run_id,
            run_id_short=(run_id or "")[:8],
            planner_message="Selecting strategy...",
            planner_visible=True,
            worker_count=worker_count,
        )
        self._needs_refresh = True
        self._live: Live | None = None
        self._manager = None
        if clarification_manager is not None:
            self.attach_clarification_manager(clarification_manager)

    def attach_clarification_manager(self, manager: Any) -> None:
        self._manager = manager
        manager.on_clarification_ready = self._handle_clarification_ready
        manager.on_queue_changed = self._on_queue_changed

    def _on_queue_changed(self, snapshot: list[dict]) -> None:
        self._needs_refresh = True

    async def _handle_clarification_ready(self, queued: Any) -> None:
        """
        Called by ClarificationManager when it's this request's turn.
        Must not return until user answers (or skips).
        """
        try:
            pending_after = 0
            try:
                pending_after = int(self._manager.pending_count()) - 1 if self._manager else 0
            except Exception:
                pending_after = 0
            if pending_after > 0:
                console.print(f"[dim]  ({pending_after} more question(s) queued after this one)[/dim]\n")
            widget = ClarificationWidget(queued.request, self.theme)
            try:
                response = await asyncio.to_thread(widget.render)
                if self._manager is not None:
                    self._manager.resolve(queued.request.request_id, response.answers)
            except KeyboardInterrupt:
                if self._manager is not None:
                    self._manager.skip(queued.request.request_id)
        finally:
            self._needs_refresh = True

    def _render(self) -> object:
        self.state.update_from_events(self.log_path)
        base = _render_live_layout(self.state)
        panel = _render_clarification_queue_panel(self._manager) if self._manager else None
        if panel is None:
            return base
        return Group(base, panel)

    async def run(self) -> RunViewState:
        with Live(self._render(), refresh_per_second=10, console=console) as live:
            self._live = live
            while not self.stop_check():
                await asyncio.sleep(self.poll_interval)
                if self._needs_refresh:
                    self._needs_refresh = False
                    live.update(self._render())
            # final
            live.update(self._render())
        self.state.finished = True
        return self.state

