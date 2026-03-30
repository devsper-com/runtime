"""
Dashboard screen: Tasks, Swarm Graph, Memory, Logs.

Shown when user presses `d`; Esc or q to return to main (prompt + output) view.
"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from devsper.tui.task_view import TaskView
from devsper.tui.task_detail_screen import TaskDetailScreen
from devsper.tui.swarm_view import SwarmView
from devsper.tui.memory_view import MemoryView
from devsper.tui.logs_view import LogsView
from devsper.tui.activity_feed_view import ActivityFeedView
from devsper.tui.knowledge_graph_view import KnowledgeGraphView
from devsper.tui.performance_view import PerformanceView
from devsper.tui.reasoning_graph_view import ReasoningGraphView
from devsper.tui.agent_role_view import AgentRoleActivityView
from devsper.tui.adaptive_tasks_view import AdaptiveTasksView
from devsper.tui.dev_view import DevView
from devsper.tui.mission_view import MissionView


class DashboardScreen(Screen[None]):
    """Full-screen dashboard: tasks, swarm graph, memory, logs. Esc to close."""

    BINDINGS = [
        ("escape", "back", "Back to chat"),
        ("q", "back", "Back to chat"),
        ("enter", "open_task_detail", "Task detail"),
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
    ReasoningGraphView, AgentRoleActivityView, AdaptiveTasksView, DevView {
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
                "  Dashboard — Tasks | Swarm | Memory | Activity | KG | Perf | Reasoning | Roles | Adaptive | Dev | Logs  —  Esc to back",
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
            with Horizontal(id="dashboard-mission-row"):
                with Vertical(classes="d-panel"):
                    yield Static("Mission View", classes="d-panel-title")
                    yield MissionView(id="mission-view")
            with Horizontal(id="dashboard-dev-row"):
                with Vertical(classes="d-panel"):
                    yield Static("Dev — Repository tree | Test results | File changes", classes="d-panel-title")
                    yield DevView(id="dev-view")
            with Vertical(id="dashboard-logs"):
                yield Static("Logs", classes="d-panel-title")
                yield LogsView(id="logs-view")

    def on_mount(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        app = self._app_ref
        events_folder = getattr(app, "_events_folder", ".devsper/events")
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
                                "description": getattr(task, "description", "") or "",
                                "status": status.lower(),
                                "runtime": "-",
                                "worker": "agent",
                                "result": getattr(task, "result", "") or "",
                                "error": getattr(task, "result", "") if status == "FAILED" else None,
                                "role": getattr(task, "role", None),
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
                from devsper.config import get_config

                cfg = get_config()
                speculative_enabled = getattr(cfg.swarm, "speculative_execution", False)
            except Exception:
                speculative_enabled = False
            try:
                from devsper.cache import TaskCache

                cache_entries = TaskCache().stats()["entries"]
            except Exception:
                cache_entries = 0
            try:
                from devsper.analytics import get_default_analytics

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
        try:
            mvw = self.query_one("#mission-view", MissionView)
            mission_snapshot = getattr(app, "_last_mission_snapshot", None) or {}
            mvw.set_mission(
                goal=mission_snapshot.get("goal", ""),
                dag=mission_snapshot.get("dag", {}),
                iteration={
                    "quality_score": mission_snapshot.get("quality_score"),
                    "iterations": mission_snapshot.get("iterations"),
                    "history": mission_snapshot.get("iteration_history", []),
                },
            )
        except Exception:
            pass

    def action_back(self) -> None:
        self.dismiss(None)

    def action_open_task_detail(self) -> None:
        """Open task detail overlay for the selected task in TaskView."""
        try:
            tv = self.query_one("#task-view", TaskView)
            task = tv.get_selected_task()
            if task:
                self.app.push_screen(TaskDetailScreen(task, self._app_ref))
        except Exception:
            pass

    def on_task_view_task_selected(self, event: TaskView.TaskSelected) -> None:
        """When TaskView emits TaskSelected (e.g. Enter on list), open detail."""
        self.app.push_screen(TaskDetailScreen(event.task, self._app_ref))
