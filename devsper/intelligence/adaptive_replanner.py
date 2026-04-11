"""
AdaptiveReplanner: mid-run re-planning when tasks fail.

Hooks into the Executor failure path to inject alternative tasks
using the existing adaptation.py utilities.
"""
from __future__ import annotations
import logging
from devsper.types.task import Task, TaskStatus
from devsper.intelligence.adaptation import create_alternative_subtasks_for_failed

log = logging.getLogger(__name__)


class AdaptiveReplanner:
    """Plugs into the Executor to re-plan after task failures."""

    def __init__(self, planner=None, max_replan_depth: int = 2) -> None:
        self._planner = planner
        self._replan_count: dict[str, int] = {}  # task_id → replan attempts
        self._max_depth = max_replan_depth

    def on_task_failed(self, failed_task: Task, scheduler) -> list[Task]:
        """
        Called when a task fails. Returns new tasks to inject into scheduler.
        Returns [] if max replan depth reached or no alternatives found.
        """
        depth = self._replan_count.get(failed_task.id, 0)
        if depth >= self._max_depth:
            log.warning(
                "[adaptive] max replan depth %d reached for task %s",
                self._max_depth,
                failed_task.id,
            )
            return []

        if self._planner is None:
            return []

        new_tasks = create_alternative_subtasks_for_failed(failed_task, self._planner, scheduler)
        if new_tasks:
            self._replan_count[failed_task.id] = depth + 1
            log.info(
                "[adaptive] replanned %d alternatives for failed task %s",
                len(new_tasks),
                failed_task.id,
            )
        return new_tasks

    def reset(self) -> None:
        self._replan_count.clear()
