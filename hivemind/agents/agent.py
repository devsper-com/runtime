from datetime import datetime

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate


PROMPT_TEMPLATE = """You are an AI worker in a distributed system.

Task:
{task_description}

Produce the best possible output."""


class Agent:
    def __init__(self, model_name: str = "default", event_log: EventLog | None = None):
        self.model_name = model_name
        self.event_log = event_log or EventLog()

    def run(self, task: Task) -> str:
        self._emit(events.AGENT_STARTED, {"task_id": task.id})
        self._emit(events.TASK_STARTED, {"task_id": task.id})

        task.status = TaskStatus.RUNNING
        prompt = PROMPT_TEMPLATE.format(task_description=task.description)
        text = generate(self.model_name, prompt)

        task.status = TaskStatus.COMPLETED
        task.result = text
        self._emit(events.TASK_COMPLETED, {"task_id": task.id})
        self._emit(events.AGENT_FINISHED, {"task_id": task.id})

        return text

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(), type=event_type, payload=payload)
        )
