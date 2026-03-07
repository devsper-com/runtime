from enum import Enum
from pydantic import BaseModel
from datetime import datetime

class events(Enum):
    SWARM_STARTED = "swarm_started"
    SWARM_FINISHED = "swarm_finished"
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    PLANNER_STARTED = "planner_started"
    PLANNER_FINISHED = "planner_finished"

class Event(BaseModel):
    timestamp: datetime
    type: events
    payload: list[str]
