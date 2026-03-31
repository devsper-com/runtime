from __future__ import annotations

from dataclasses import dataclass

from devsper.swarm.scheduler import Scheduler
from devsper.types.task import Task


@dataclass(frozen=True)
class SpeculativePlan:
    parent_task_id: str
    predicted_tasks: list[Task]


class SpeculativePlanner:
    """Predict follow-up tasks and stage speculative execution."""

    def __init__(self, max_predictions: int = 2) -> None:
        self._max_predictions = max(0, int(max_predictions))
        self._lineage: dict[str, set[str]] = {}

    def predict_next(self, completed_task: Task, scheduler: Scheduler) -> SpeculativePlan | None:
        successors = scheduler.get_successors(completed_task.id)
        predicted: list[Task] = []
        for sid in successors[: self._max_predictions]:
            try:
                task = scheduler.get_task(sid)
            except Exception:
                continue
            if getattr(task, "result", None):
                continue
            task.speculative = True
            predicted.append(task)
        if not predicted:
            return None
        self._lineage[completed_task.id] = {t.id for t in predicted}
        return SpeculativePlan(parent_task_id=completed_task.id, predicted_tasks=predicted)

    def cancel_unused(self, parent_task_id: str, scheduler: Scheduler) -> list[str]:
        ids = sorted(self._lineage.pop(parent_task_id, set()))
        cancelled: list[str] = []
        for tid in ids:
            try:
                t = scheduler.get_task(tid)
            except Exception:
                continue
            if getattr(t, "status", None).name == "PENDING":
                t.speculative = False
                cancelled.append(tid)
        return cancelled

