"""
PriorityScheduler: extends Scheduler with priority-aware task ordering.
get_ready_tasks() returns tasks sorted by priority, then dependency impact, then estimated duration.
"""

from hivemind.swarm.scheduler import Scheduler
from hivemind.types.task import Task, TaskStatus


class PriorityScheduler(Scheduler):
    """Scheduler that orders ready tasks by priority (1=highest), then by dependency impact, then shortest first."""

    def __init__(self, run_id: str = "") -> None:
        super().__init__(run_id=run_id)
        self._priority: dict[str, int] = {}  # task_id -> priority (lower = higher priority)

    def add_task(self, task: Task, priority: int = 5) -> None:
        """Add a single task with optional priority (1-10, default 5)."""
        if not (1 <= priority <= 10):
            priority = max(1, min(10, priority))
        self._priority[task.id] = priority
        super().add_tasks([task])

    def add_tasks(self, tasks: list[Task]) -> None:
        """Add tasks; each task gets priority from task.priority if present, else 5."""
        for t in tasks:
            if t.id not in self._priority:
                p = getattr(t, "priority", 5)
                self._priority[t.id] = max(1, min(10, p)) if isinstance(p, int) else 5
        super().add_tasks(tasks)

    def bump_priority(self, task_id: str, new_priority: int) -> None:
        """Set priority for a task (e.g. for SLA escalation). Lower number = higher priority."""
        if task_id in self._tasks:
            self._priority[task_id] = max(1, min(10, new_priority))

    def _priority_of(self, task_id: str) -> int:
        return self._priority.get(task_id, 5)

    def get_ready_tasks(self) -> list[Task]:
        """Return ready tasks sorted by: 1) priority (lower first), 2) dependencies satisfied count (unblock more first), 3) estimated duration (shortest first)."""
        ready = super().get_ready_tasks()
        if not ready:
            return ready

        def unblock_count(task_id: str) -> int:
            return len(list(self._graph.successors(task_id)))

        def estimated_duration(task: Task) -> float:
            # Heuristic: length of description as proxy for duration
            desc = task.description or ""
            return float(len(desc))

        ready.sort(
            key=lambda t: (
                self._priority_of(t.id),
                -unblock_count(t.id),  # higher successor count first
                estimated_duration(t),
            )
        )
        return ready
