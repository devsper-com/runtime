"""
Task panel: task_id, status, runtime, worker agent.

Data can come from last scheduler or from event stream (task_started, task_completed).
"""

from textual.widgets import Static
from textual.reactive import reactive


class TaskView(Static):
    """Displays list of tasks with status, runtime, worker."""

    tasks_data: reactive[list[dict]] = reactive(list)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tasks: list[dict] = []

    def set_tasks(self, tasks: list[dict]) -> None:
        """Update tasks. Each dict: task_id, status, runtime (str), worker (str)."""
        self._tasks = tasks
        self.tasks_data = tasks

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

    def watch_tasks_data(self, data: list[dict]) -> None:
        self._tasks = data
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self._tasks:
            self.update(
                "No tasks yet.\n\n"
                "↑ Type your task in the prompt bar above,\n"
                "  then press Enter or r to run."
            )
            return
        lines = []
        for t in self._tasks:
            tid = t.get("task_id", "?")
            status = t.get("status", "pending")
            runtime = t.get("runtime", "-")
            worker = t.get("worker", "-")
            lines.append(f"{tid} {status}")
            lines.append(f"  runtime: {runtime}  worker: {worker}")
        self.update("\n".join(lines) if lines else "(no tasks)")

    def on_mount(self) -> None:
        self._refresh_display()
