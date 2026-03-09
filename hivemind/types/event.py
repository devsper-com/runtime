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
    TASK_CACHE_HIT = "task_cache_hit"  # v1.6: payload task_id, similarity, original_description
    TASK_CACHE_MISS = "task_cache_miss"  # v1.6: payload task_id
    TASK_MODEL_SELECTED = "task_model_selected"  # v1.6: payload task_id, tier, model
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    PLANNER_STARTED = "planner_started"
    PLANNER_FINISHED = "planner_finished"
    EXECUTOR_STARTED = "executor_started"
    EXECUTOR_FINISHED = "executor_finished"
    TOOL_CALLED = "tool_called"
    REASONING_NODE_ADDED = "reasoning_node_added"
    USER_INJECTION = "user_injection"
    # v1.7
    TASK_CRITIQUED = "task_critiqued"
    AGENT_BROADCAST = "agent_broadcast"
    PREFETCH_HIT = "prefetch_hit"
    PREFETCH_MISS = "prefetch_miss"
    TASK_STRUCTURED_OUTPUT_CORRECTED = "task_structured_output_corrected"
    # v1.8
    PLANNER_KG_CONTEXT_INJECTED = "planner_kg_context_injected"
    KNOWLEDGE_EXTRACTED = "knowledge_extracted"
    MEMORY_CONSOLIDATED = "memory_consolidated"

class Event(BaseModel):
    timestamp: datetime
    type: events
    payload: dict
