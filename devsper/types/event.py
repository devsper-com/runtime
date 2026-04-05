import json
from datetime import datetime, timezone
from enum import Enum
import hashlib
import uuid
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
    # Clarification (human-in-the-loop)
    CLARIFICATION_NEEDED = "clarification_needed"
    # Cloud/swarmworker SSE — agent blocked until user answers via platform/CLI
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_RECEIVED = "clarification_received"
    RUN_MANIFEST_EMITTED = "run_manifest_emitted"
    BUDGET_WARNING = "budget_warning"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    # Worker / DAG visibility (platform + local)
    WORKER_ASSIGNED = "worker_assigned"
    # Speculative branch (alias TASK_CREATED speculative flag; explicit lifecycle)
    SPECULATIVE_STARTED = "speculative_started"
    SPECULATIVE_CANCELLED = "speculative_cancelled"
    # HITL (alias clarification_* for UI contract; both may be emitted)
    HITL_REQUESTED = "hitl_requested"
    HITL_RESOLVED = "hitl_resolved"

class Event(BaseModel):
    timestamp: datetime
    type: events
    payload: dict
    event_id: str = ""
    sequence_id: int | None = None

    @model_validator(mode="after")
    def _payload_must_be_json_safe(self) -> "Event":
        try:
            json.dumps(self.payload)
        except TypeError as e:
            raise EventSerializationError(f"Event payload not JSON-safe: {e}") from e
        if not self.event_id:
            # Deterministic when request/task identity exists; random fallback otherwise.
            identity = (
                str(self.payload.get("request_id") or "").strip()
                or str(self.payload.get("task_id") or "").strip()
                or str(self.payload.get("node_id") or "").strip()
            )
            if identity:
                base = f"{self.type.value}:{identity}:{json.dumps(self.payload, sort_keys=True, default=str)}"
                self.event_id = hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
            else:
                self.event_id = uuid.uuid4().hex
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
            "event_id": self.event_id,
            "sequence_id": self.sequence_id,
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
            event_id=str(data.get("event_id") or ""),
            sequence_id=(int(data.get("sequence_id")) if data.get("sequence_id") is not None else None),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        return cls.from_dict(json.loads(raw))
