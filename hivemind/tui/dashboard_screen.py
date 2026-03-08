"""
Dashboard screen: Tasks, Swarm Graph, Memory, Logs.

Shown when user presses `d`; Esc or q to return to main (prompt + output) view.
"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from hivemind.tui.task_view import TaskView
from hivemind.tui.swarm_view import SwarmView
from hivemind.tui.memory_view import MemoryView
from hivemind.tui.logs_view import LogsView


class DashboardScreen(Screen[None]):
    """Full-screen dashboard: tasks, swarm graph, memory, logs. Esc to close."""

    BINDINGS = [
        ("escape", "back", "Back to chat"),
        ("q", "back", "Back to chat"),
    ]

    CSS = """
    #dashboard-container {
        height: 100%;
        padding: 0 2 1 2;
        layout: vertical;
    }
    #dashboard-header {
        color: #6EE7B7;
        text-style: bold;
        padding: 1 2;
        margin-bottom: 1;
        border: heavy #6EE7B7;
    }
    #dashboard-top {
        height: 1fr;
        min-height: 10;
    }
    .d-panel {
        width: 1fr;
        height: 1fr;
        min-height: 6;
        border: solid #6EE7B7;
        padding: 1 2;
        margin: 0 1 1 1;
    }
    .d-panel-title {
        text-style: bold;
        color: #6EE7B7;
        margin-bottom: 1;
    }
    #dashboard-logs {
        height: 1fr;
        min-height: 6;
        border: solid #6EE7B7;
        padding: 1 2;
        margin: 0 1 1 1;
    }
    TaskView, SwarmView, MemoryView, LogsView {
        scrollbar-size: 1 1;
        overflow-y: auto;
        height: 1fr;
    }
    """

    def __init__(
        self,
        app_ref: object,
        event_log_path: str | None = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._app_ref = app_ref
        self._event_log_path = event_log_path

    def compose(self) -> ComposeResult:
        with Container(id="dashboard-container"):
            yield Static(
                "  Dashboard — Tasks | Swarm Graph | Memory | Logs  —  Press Esc to back to chat",
                id="dashboard-header",
            )
            with Horizontal(id="dashboard-top"):
                with Vertical(classes="d-panel"):
                    yield Static("Tasks", classes="d-panel-title")
                    yield TaskView(id="task-view")
                with Vertical(classes="d-panel"):
                    yield Static("Swarm Graph", classes="d-panel-title")
                    yield SwarmView(id="swarm-view")
                with Vertical(classes="d-panel"):
                    yield Static("Memory", classes="d-panel-title")
                    yield MemoryView(id="memory-view")
            with Vertical(id="dashboard-logs"):
                yield Static("Logs", classes="d-panel-title")
                yield LogsView(id="logs-view")

    def on_mount(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        app = self._app_ref
        events_folder = getattr(app, "_events_folder", ".hivemind/events")
        try:
            lv = self.query_one("#logs-view", LogsView)
            lv.set_events_folder(events_folder)
            if getattr(self, "_event_log_path", None):
                lv.set_log_path(self._event_log_path)
            lv.refresh_logs()
        except Exception:
            pass
        try:
            mv = self.query_one("#memory-view", MemoryView)
            mv.load_from_store()
        except Exception:
            pass
        scheduler = getattr(app, "_last_scheduler", None)
        if scheduler is not None:
            try:
                sv = self.query_one("#swarm-view", SwarmView)
                sv.set_scheduler(scheduler)
            except Exception:
                pass
            tasks = []
            try:
                graph = scheduler._graph
                for nid in graph.nodes():
                    task = scheduler._tasks.get(nid)
                    if task:
                        status = getattr(task.status, "name", str(task.status))
                        tasks.append({
                            "task_id": task.id,
                            "status": status.lower(),
                            "runtime": "-",
                            "worker": "agent",
                        })
            except Exception:
                pass
            if tasks:
                try:
                    tv = self.query_one("#task-view", TaskView)
                    tv.set_tasks(tasks)
                except Exception:
                    pass

    def action_back(self) -> None:
        self.dismiss(None)
