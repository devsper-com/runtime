from __future__ import annotations

import threading

from devsper.swarm.scheduler import Scheduler
from devsper.types.task import Task, TaskStatus


class RuntimeStateManager:
    """Concurrency-safe facade over Scheduler task state."""

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
        self._lock = threading.RLock()

    def next_ready_tasks(self, limit: int) -> list[Task]:
        with self._lock:
            ready = self._scheduler.get_ready_tasks()
            out: list[Task] = []
            for task in ready:
                if len(out) >= max(0, int(limit)):
                    break
                if task.status != TaskStatus.PENDING:
                    continue
                task.status = TaskStatus.RUNNING
                out.append(task)
            return out

    def mark_completed(self, task_id: str, result: str) -> None:
        with self._lock:
            self._scheduler.mark_completed(task_id, result)

    def mark_failed(self, task_id: str, error: str) -> None:
        with self._lock:
            self._scheduler.mark_failed(task_id, error)

    def is_finished(self) -> bool:
        with self._lock:
            return self._scheduler.is_finished()

    def all_tasks(self) -> list[Task]:
        with self._lock:
            return self._scheduler.get_all_tasks()

    def add_tasks(self, tasks: list[Task]) -> None:
        with self._lock:
            self._scheduler.add_tasks(tasks)

    def append_task_context(self, task_id: str, text: str) -> None:
        with self._lock:
            self._scheduler.append_task_context(task_id, text)

