"""
Planner: convert one task into multiple ordered subtasks.

Lifecycle: PLANNER_STARTED → TASK_CREATED (×N) → PLANNER_FINISHED.
Subtasks have sequential dependencies; each subtask gets a short unique ID.
"""

import re
import secrets
from datetime import datetime, timezone

from hivemind.types.task import Task
from hivemind.types.event import Event, events
from hivemind.agents.roles import infer_role_from_description
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate


PLANNER_PROMPT = """Break the following task into 5 smaller steps.

Task:
{task_description}
{kg_section}

Return a numbered list.

Example format:
1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step"""

EXPAND_TASKS_PROMPT = """A task just completed in a workflow.

Completed task: {task_description}
Result (preview): {result_preview}

Suggest 0 to 3 additional follow-up tasks that would extend or build on this work.
Return a numbered list only. One task per line.
Example:
1. Compare methods
2. Identify trends
"""


NUMBERED_LINE = re.compile(r"^\s*\d+[.)]\s*(.+)$", re.MULTILINE)


def _short_id() -> str:
    """Return a short, URL-safe task id (8 hex chars)."""
    return secrets.token_hex(4)


class Planner:
    """Converts one Task into a list of subtasks with sequential dependencies."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        event_log: EventLog | None = None,
        strategy=None,
        prompt_suffix: str = "",
        knowledge_graph=None,
        guide_planning: bool = False,
        min_confidence: float = 0.30,
    ):
        self.model_name = model_name
        self.event_log = event_log or EventLog()
        self.strategy = strategy
        self.prompt_suffix = prompt_suffix or ""
        self.knowledge_graph = knowledge_graph
        self.guide_planning = guide_planning
        self.min_confidence = min_confidence

    def plan(self, task: Task) -> list[Task]:
        """Break task into subtasks (strategy DAG or LLM). Emit planner lifecycle events."""
        self._emit(events.PLANNER_STARTED, {"task_id": task.id})

        if self.strategy is not None:
            subtasks = self.strategy.plan(task)
            if subtasks:
                for st in subtasks:
                    if getattr(st, "role", None) is None:
                        st.role = infer_role_from_description(st.description or "")
                    self._emit(events.TASK_CREATED, {"task_id": st.id, "description": st.description})
                self._emit(events.PLANNER_FINISHED, {"task_id": task.id, "subtask_count": len(subtasks)})
                return subtasks

        task_description = (task.description or "") + self.prompt_suffix
        kg_section = ""
        if self.guide_planning and self.knowledge_graph is not None:
            from hivemind.knowledge.query import query_for_planning, format_planning_context
            planning_ctx = query_for_planning(self.knowledge_graph, task_description)
            if planning_ctx.confidence > self.min_confidence:
                kg_section = "\n\n## Relevant prior knowledge:\n" + format_planning_context(planning_ctx) + "\n\nUse this to avoid re-discovering known facts."
                self._emit(
                    events.PLANNER_KG_CONTEXT_INJECTED,
                    {
                        "concept_count": len(planning_ctx.relevant_concepts),
                        "finding_count": len(planning_ctx.prior_findings),
                        "confidence": planning_ctx.confidence,
                    },
                )
        prompt = PLANNER_PROMPT.format(task_description=task_description, kg_section=kg_section or "")
        raw = generate(self.model_name, prompt)
        steps = self._parse_numbered_list(raw)

        subtasks: list[Task] = []
        task_ids: list[str] = []
        for i, description in enumerate(steps, start=1):
            task_id = _short_id()
            task_ids.append(task_id)
            deps = [task_ids[i - 2]] if i > 1 else []
            role = infer_role_from_description(description.strip())
            subtask = Task(id=task_id, description=description.strip(), dependencies=deps, role=role)
            subtasks.append(subtask)
            self._emit(
                events.TASK_CREATED,
                {"task_id": task_id, "description": subtask.description},
            )

        self._emit(events.PLANNER_FINISHED, {"task_id": task.id, "subtask_count": len(subtasks)})
        return subtasks

    def expand_tasks(self, completed_task: Task, context: list[Task] | None = None) -> list[Task]:
        """
        After a task completes, optionally generate additional tasks (dynamic DAG growth).
        New tasks depend on the completed task. Emits TASK_CREATED for each.
        """
        result_preview = (completed_task.result or "")[:500]
        prompt = EXPAND_TASKS_PROMPT.format(
            task_description=completed_task.description,
            result_preview=result_preview,
        )
        raw = generate(self.model_name, prompt)
        steps = self._parse_numbered_list(raw)
        if not steps:
            return []

        new_tasks: list[Task] = []
        for i, description in enumerate(steps, start=1):
            task_id = _short_id()
            role = infer_role_from_description(description.strip())
            subtask = Task(
                id=task_id,
                description=description.strip(),
                dependencies=[completed_task.id],
                role=role,
            )
            new_tasks.append(subtask)
            self._emit(events.TASK_CREATED, {"task_id": task_id, "description": subtask.description})

        return new_tasks

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
