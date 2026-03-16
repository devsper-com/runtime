"""
Task panel: task_id, status, runtime, worker agent.

Data can come from last scheduler or from event stream (task_started, task_completed).
Arrow-key selection and Enter opens task detail overlay.
"""

from textual.widgets import Static, ListView, ListItem, Label
from textual.reactive import reactive
from textual.message import Message


class TaskView(Static):
    """Displays list of tasks with status; select with arrows, Enter for detail."""

    tasks_data: reactive[list[dict]] = reactive(list)

    class TaskSelected(Message):
        """Emitted when user presses Enter on a selected task."""
        def __init__(self, task: dict) -> None:
            self.task = task
            super().__init__()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tasks: list[dict] = []
        self._list_view: ListView | None = None

    def compose(self):
        from textual.containers import VerticalScroll
        with VerticalScroll():
            self._list_view = ListView(id="task-list-view")
            yield self._list_view

    def set_tasks(self, tasks: list[dict]) -> None:
        """Update tasks. Each dict: task_id, status, runtime (str), worker (str), and optionally description, result, error."""
        self._tasks = tasks
        self.tasks_data = tasks
        self._refresh_list()

    def add_or_update_task(
        self, task_id: str, status: str, runtime: str = "-", worker: str = "agent"
    ) -> None:
        """Add or update a single task (e.g. from events)."""
        for t in self._tasks:
            if t.get("task_id") == task_id:
                t["status"] = status
                t["runtime"] = runtime
                t["worker"] = worker
                self.tasks_data = list(self._tasks)
                self._refresh_list()
                return
        self._tasks.append(
            {
                "task_id": task_id,
                "status": status,
                "runtime": runtime,
                "worker": worker,
            }
        )
        self.tasks_data = list(self._tasks)
        self._refresh_list()

    def watch_tasks_data(self, data: list[dict]) -> None:
        self._tasks = data
        self._refresh_list()

    def _refresh_list(self) -> None:
        try:
            lv = self.query_one("#task-list-view", ListView)
        except Exception:
            return
        try:
            lv.clear_children()
        except Exception:
            pass
        if not self._tasks:
            return
        for t in self._tasks:
            tid = t.get("task_id", "?")
            status = t.get("status", "pending")
            desc = (t.get("description") or tid)[:50]
            item = ListItem(Label(f"{tid}  {status}  {desc}"), id=f"task-{tid}")
            lv.append(item)

    def get_selected_task(self) -> dict | None:
        """Return the currently selected task dict, or None."""
        try:
            lv = self.query_one("#task-list-view", ListView)
            idx = lv.index
            if idx is not None and 0 <= idx < len(self._tasks):
                return self._tasks[idx]
        except Exception:
            pass
        return None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = getattr(event.list_view, "index", None)
        if idx is not None and 0 <= idx < len(self._tasks):
            self.post_message(self.TaskSelected(self._tasks[idx]))

    def on_mount(self) -> None:
        self._refresh_list()
