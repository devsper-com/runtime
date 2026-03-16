import json
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, model_validator

from devsper.types.exceptions import EventSerializationError


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
    # v2.0
    PROVIDER_FALLBACK = "provider_fallback"
    # v2.1
    TASK_REJECTED_BY_HUMAN = "task_rejected_by_human"

class Event(BaseModel):
    timestamp: datetime
    type: events
    payload: dict

    @model_validator(mode="after")
    def _payload_must_be_json_safe(self) -> "Event":
        try:
            json.dumps(self.payload)
        except TypeError as e:
            raise EventSerializationError(f"Event payload not JSON-safe: {e}") from e
        return self

    def to_dict(self) -> dict:
        ts = self.timestamp
        if hasattr(ts, "isoformat"):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts)
        type_val = self.type.value if hasattr(self.type, "value") else str(self.type)
        return {
            "timestamp": ts_str,
            "type": type_val,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        ts = data.get("timestamp", "")
        if isinstance(ts, str):
            try:
                if ts.endswith("Z"):
                    ts = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
            except ValueError:
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        type_val = data.get("type", "swarm_started")
        try:
            event_type = events(type_val) if isinstance(type_val, str) else events.SWARM_STARTED
        except ValueError:
            event_type = events.SWARM_STARTED
        return cls(
            timestamp=dt,
            type=event_type,
            payload=dict(data.get("payload", {})),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        return cls.from_dict(json.loads(raw))
