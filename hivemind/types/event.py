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
    EXECUTOR_STARTED = "executor_started"
    EXECUTOR_FINISHED = "executor_finished"
    TOOL_CALLED = "tool_called"
    REASONING_NODE_ADDED = "reasoning_node_added"

class Event(BaseModel):
    timestamp: datetime
    type: events
    payload: dict
