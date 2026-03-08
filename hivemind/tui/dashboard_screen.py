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
from hivemind.tui.activity_feed_view import ActivityFeedView
from hivemind.tui.knowledge_graph_view import KnowledgeGraphView
from hivemind.tui.performance_view import PerformanceView
from hivemind.tui.reasoning_graph_view import ReasoningGraphView
from hivemind.tui.agent_role_view import AgentRoleActivityView
from hivemind.tui.adaptive_tasks_view import AdaptiveTasksView


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
    #dashboard-mid {
        height: 1fr;
        min-height: 8;
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
    # v1.2 panels
    #dashboard-reasoning-row { height: auto; min-height: 6; }
    TaskView, SwarmView, MemoryView, LogsView, ActivityFeedView, KnowledgeGraphView, PerformanceView,
    ReasoningGraphView, AgentRoleActivityView, AdaptiveTasksView {
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
                "  Dashboard — Tasks | Swarm | Memory | Activity | KG | Perf | Reasoning | Roles | Adaptive | Logs  —  Esc to back",
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
            with Horizontal(id="dashboard-mid"):
                with Vertical(classes="d-panel"):
                    yield Static("Activity Feed", classes="d-panel-title")
                    yield ActivityFeedView(id="activity-feed-view")
                with Vertical(classes="d-panel"):
                    yield Static("Knowledge Graph", classes="d-panel-title")
                    yield KnowledgeGraphView(id="knowledge-graph-view")
                with Vertical(classes="d-panel"):
                    yield Static(
                        "Performance (speculative | cache | tools)",
                        classes="d-panel-title",
                    )
                    yield PerformanceView(id="performance-view")
            with Horizontal(id="dashboard-reasoning-row"):
                with Vertical(classes="d-panel"):
                    yield Static("Reasoning Graph", classes="d-panel-title")
                    yield ReasoningGraphView(id="reasoning-graph-view")
                with Vertical(classes="d-panel"):
                    yield Static("Agent Role Activity", classes="d-panel-title")
                    yield AgentRoleActivityView(id="agent-role-view")
                with Vertical(classes="d-panel"):
                    yield Static("Adaptive Task Creation", classes="d-panel-title")
                    yield AdaptiveTasksView(id="adaptive-tasks-view")
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
            af = self.query_one("#activity-feed-view", ActivityFeedView)
            af.set_events_folder(events_folder)
            if getattr(self, "_event_log_path", None):
                af.set_log_path(self._event_log_path)
            af.refresh_events()
        except Exception:
            pass
        try:
            kg = self.query_one("#knowledge-graph-view", KnowledgeGraphView)
            kg.load_from_memory()
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
                        tasks.append(
                            {
                                "task_id": task.id,
                                "status": status.lower(),
                                "runtime": "-",
                                "worker": "agent",
                            }
                        )
            except Exception:
                pass
            if tasks:
                try:
                    tv = self.query_one("#task-view", TaskView)
                    tv.set_tasks(tasks)
                except Exception:
                    pass
        try:
            pv = self.query_one("#performance-view", PerformanceView)
            speculative_count = 0
            if scheduler is not None:
                speculative_count = sum(
                    1
                    for t in scheduler._tasks.values()
                    if getattr(t, "speculative", False)
                )
            try:
                from hivemind.config import get_config

                cfg = get_config()
                speculative_enabled = getattr(cfg.swarm, "speculative_execution", False)
            except Exception:
                speculative_enabled = False
            try:
                from hivemind.cache import TaskCache

                cache_entries = TaskCache().stats()["entries"]
            except Exception:
                cache_entries = 0
            try:
                from hivemind.analytics import get_default_analytics

                tool_stats = get_default_analytics().get_stats()
            except Exception:
                tool_stats = None
            pv.set_stats(
                speculative_enabled=speculative_enabled,
                speculative_count=speculative_count,
                cache_entries=cache_entries,
                tool_stats=tool_stats,
            )
        except Exception:
            pass
        # v1.2: reasoning graph, agent roles, adaptive tasks
        try:
            rgv = self.query_one("#reasoning-graph-view", ReasoningGraphView)
            reasoning_store = getattr(app, "_last_reasoning_store", None)
            rgv.set_reasoning_store(reasoning_store)
            rgv.load_from_store()
        except Exception:
            pass
        try:
            arv = self.query_one("#agent-role-view", AgentRoleActivityView)
            tasks_with_roles = []
            if scheduler is not None:
                for t in scheduler._tasks.values():
                    tasks_with_roles.append({
                        "task_id": t.id,
                        "role": getattr(t, "role", None),
                        "status": getattr(t.status, "name", str(t.status)),
                    })
            arv.set_tasks_with_roles(tasks_with_roles)
        except Exception:
            pass
        try:
            atv = self.query_one("#adaptive-tasks-view", AdaptiveTasksView)
            atv.set_events_folder(events_folder)
            atv.set_log_path(getattr(self, "_event_log_path", None))
            atv.refresh_adaptive_events()
        except Exception:
            pass

    def action_back(self) -> None:
        self.dismiss(None)
