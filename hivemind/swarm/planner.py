"""
Planner: convert one task into multiple ordered subtasks.

Lifecycle: PLANNER_STARTED → TASK_CREATED (×N) → PLANNER_FINISHED.
Subtasks have sequential dependencies: task_n depends on task_(n-1).
"""

import re
from datetime import datetime, timezone

from hivemind.types.task import Task
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate


PLANNER_PROMPT = """Break the following task into 5 smaller steps.

Task:
{task_description}

Return a numbered list.

Example format:
1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step"""


# Matches lines like "1. step text" or "2) step text"
NUMBERED_LINE = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)


class Planner:
    """Converts one Task into a list of subtasks with sequential dependencies."""

    def __init__(self, model_name: str = "default", event_log: EventLog | None = None):
        self.model_name = model_name
        self.event_log = event_log or EventLog()

    def plan(self, task: Task) -> list[Task]:
        """Break task into 5 subtasks. Emit planner lifecycle events."""
        self._emit(events.PLANNER_STARTED, {"task_id": task.id})

        prompt = PLANNER_PROMPT.format(task_description=task.description)
        raw = generate(self.model_name, prompt)
        steps = self._parse_numbered_list(raw)

        subtasks: list[Task] = []
        for i, description in enumerate(steps, start=1):
            task_id = f"task_{i}"
            deps = [f"task_{i - 1}"] if i > 1 else []
            subtask = Task(id=task_id, description=description.strip(), dependencies=deps)
            subtasks.append(subtask)
            self._emit(
                events.TASK_CREATED,
                {"task_id": task_id, "description": subtask.description},
            )

        self._emit(events.PLANNER_FINISHED, {"task_id": task.id, "subtask_count": len(subtasks)})
        return subtasks

    def _parse_numbered_list(self, text: str) -> list[str]:
        """Parse '1. step\\n2. step' into ['step', 'step', ...]."""
        steps = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            m = NUMBERED_LINE.match(line)
            if m:
                steps.append(m.group(1).strip())
        return steps

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
