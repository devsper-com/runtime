"""
Scheduler: manage the task DAG and determine which tasks are runnable.

Supports: add_tasks, get_ready_tasks, mark_completed, is_finished.
"""

import networkx as nx

from hivemind.types.task import Task, TaskStatus


class Scheduler:
    """Manages a DAG of tasks. Tracks dependencies and exposes runnable tasks."""

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._tasks: dict[str, Task] = {}

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

    def mark_completed(self, task_id: str) -> None:
        """Mark a task completed so dependent tasks can become runnable."""
        if task_id in self._tasks:
            self._tasks[task_id].status = TaskStatus.COMPLETED

    def is_finished(self) -> bool:
        """Return True if every task is completed."""
        return all(t.status == TaskStatus.COMPLETED for t in self._tasks.values())

    def get_results(self) -> dict[str, str]:
        """Return task_id -> result for all completed tasks."""
        return {
            task_id: (t.result or "")
            for task_id, t in self._tasks.items()
            if t.status == TaskStatus.COMPLETED and t.result is not None
        }

    def get_completed_tasks(self) -> list[Task]:
        """Return all completed tasks (for learning/memory storage)."""
        return [
            t
            for t in self._tasks.values()
            if t.status == TaskStatus.COMPLETED and t.result is not None
        ]
