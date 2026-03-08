"""Base strategy: produce a DAG of tasks from a root task."""

from abc import ABC, abstractmethod

from hivemind.types.task import Task


class Strategy(ABC):
    """Strategy produces a list of tasks with dependencies (DAG) for the scheduler."""

    @abstractmethod
    def plan(self, root_task: Task) -> list[Task]:
        """Return subtasks with dependencies. Empty list means fall back to LLM planner."""
        ...
