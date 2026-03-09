"""
Scheduler: manage the task DAG and determine which tasks are runnable.

Supports: add_tasks, get_ready_tasks, get_speculative_tasks, mark_completed,
confirm_speculative_for, discard_speculative_for, is_finished.
v1.9: Single source of truth — get_task, get_all_tasks, get_results, snapshot, restore.
"""

from datetime import datetime, timezone
import networkx as nx

from hivemind.types.task import Task, TaskStatus
from hivemind.types.exceptions import TaskNotFoundError
from hivemind.swarm.speculation import (
    get_speculative_candidates,
    confirm_speculative,
    discard_speculative,
)


class Scheduler:
    """Manages a DAG of tasks. Tracks dependencies and exposes runnable tasks. Single source of truth for task state."""

    def __init__(self, run_id: str = "") -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._tasks: dict[str, Task] = {}
        self.run_id = run_id

    def get_task(self, task_id: str) -> Task:
        """Return task by id. Raises TaskNotFoundError if not found."""
        if task_id not in self._tasks:
            raise TaskNotFoundError(f"Task not found: {task_id!r}")
        return self._tasks[task_id]

    def get_all_tasks(self) -> list[Task]:
        """Return all tasks."""
        return list(self._tasks.values())

    def add_tasks(self, tasks: list[Task]) -> None:
        """Add tasks and build the internal dependency graph."""
        for task in tasks:
            self._tasks[task.id] = task
            self._graph.add_node(task.id)
        for task in tasks:
            for dep in task.dependencies:
                if dep not in self._tasks:
                    raise ValueError(f"Unknown dependency: {dep!r}")
                self._graph.add_edge(dep, task.id)
        if not nx.is_directed_acyclic_graph(self._graph):
            raise ValueError("Task graph contains a cycle")

    def get_ready_tasks(self) -> list[Task]:
        """Return tasks that are runnable: PENDING and all dependencies completed."""
        ready: list[Task] = []
        for task_id, task in self._tasks.items():
            if task.status != TaskStatus.PENDING:
                continue
            deps = list(self._graph.predecessors(task_id))
            if all(self._tasks[dep].status == TaskStatus.COMPLETED for dep in deps):
                ready.append(task)
        return ready

    def mark_completed(self, task_id: str, result: str = "") -> None:
        """Mark a task completed and set its result. Dependent tasks can become runnable."""
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.COMPLETED
            t.result = result

    def mark_failed(self, task_id: str, error: str = "") -> None:
        """Mark a task failed and set its error."""
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = TaskStatus.FAILED
            t.error = error

    def is_finished(self) -> bool:
        """Return True when every task is completed or failed (no pending/running left)."""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            for t in self._tasks.values()
        )

    def get_results(self) -> dict[str, str]:
        """Return task_id -> result for completed tasks only."""
        return {
            task_id: (t.result or "")
            for task_id, t in self._tasks.items()
            if t.status == TaskStatus.COMPLETED and t.result is not None
        }

    def snapshot(self) -> dict:
        """Full serializable state for checkpointing and node sync."""
        edges = list(self._graph.edges())
        tasks_data = [t.to_dict() for t in self._tasks.values()]
        completed_count = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed_count = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        return {
            "run_id": self.run_id,
            "tasks": tasks_data,
            "edges": [[str(u), str(v)] for u, v in edges],
            "completed_count": completed_count,
            "failed_count": failed_count,
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def restore(cls, snapshot: dict) -> "Scheduler":
        """Reconstruct Scheduler from snapshot dict."""
        run_id = snapshot.get("run_id", "")
        s = cls(run_id=run_id)
        tasks_data = snapshot.get("tasks", [])
        for tdata in tasks_data:
            task = Task.from_dict(tdata)
            s._tasks[task.id] = task
            s._graph.add_node(task.id)
        for edge in snapshot.get("edges", []):
            if len(edge) >= 2:
                u, v = str(edge[0]), str(edge[1])
                if u in s._tasks and v in s._tasks:
                    s._graph.add_edge(u, v)
        return s

    def get_completed_tasks(self) -> list[Task]:
        """Return all completed tasks (for learning/memory storage)."""
        return [
            t
            for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED and t.result is not None
        ]

    def get_speculative_tasks(self) -> list[Task]:
        """Return tasks that can be run speculatively (one dep running, rest completed)."""
        candidates = get_speculative_candidates(self._tasks, self._graph)
        for t in candidates:
            t.speculative = True
        return candidates

    def get_successors(self, task_id: str) -> list[str]:
        """Return task ids that depend on the given task."""
        return list(self._graph.successors(task_id))

    def confirm_speculative_for(self, completed_task_id: str) -> None:
        """When completed_task_id finishes, confirm its speculative successors (keep results)."""
        for sid in self.get_successors(completed_task_id):
            if sid in self._tasks:
                confirm_speculative(self._tasks[sid])

    def discard_speculative_for(self, failed_task_id: str) -> None:
        """When failed_task_id fails, discard results of speculative successors."""
        for sid in self.get_successors(failed_task_id):
            if sid in self._tasks:
                discard_speculative(self._tasks[sid])
