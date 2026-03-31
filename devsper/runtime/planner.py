from __future__ import annotations

from dataclasses import dataclass

from devsper.swarm.planner import Planner
from devsper.types.task import Task


@dataclass(frozen=True)
class DynamicTaskBatch:
    parent_task_id: str
    tasks: list[Task]


class RuntimePlanner:
    """Runtime wrapper for safe dynamic task injection."""

    def __init__(self, planner: Planner | None) -> None:
        self._planner = planner

    def expand(self, completed_task: Task) -> DynamicTaskBatch | None:
        if self._planner is None:
            return None
        new_tasks = self._planner.expand_tasks(completed_task)
        if not new_tasks:
            return None
        return DynamicTaskBatch(parent_task_id=completed_task.id, tasks=new_tasks)

