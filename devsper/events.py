"""
Structured clarification protocol: types and event names for human-in-the-loop.
"""

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass
class ClarificationField:
    type: Literal["mcq", "multi_select", "text", "confirm", "rank"]
    question: str
    options: list[str] | None  # for mcq, multi_select, rank
    default: str | None  # pre-filled value
    required: bool  # if False, user can skip

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClarificationRequest:
    request_id: str  # uuid, used to match response
    task_id: str
    agent_role: str
    fields: list[Any]  # list of ClarificationField or dict (when from payload)
    context: str  # why the agent is asking (1 sentence)
    priority: int = 1  # 0=blocking, 1=normal, 2=optional
    timeout_seconds: int = 120  # auto-proceed with defaults after timeout

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "task_id": self.task_id,
            "agent_role": self.agent_role,
            "fields": [f.to_dict() if hasattr(f, "to_dict") else f for f in self.fields],
            "context": self.context,
            "priority": int(self.priority) if self.priority is not None else 1,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClarificationRequest":
        raw_fields = data.get("fields", [])
        fields = []
        for f in raw_fields:
            if isinstance(f, dict):
                fields.append(f)
            elif hasattr(f, "to_dict"):
                fields.append(f.to_dict())
            else:
                fields.append(f)
        return cls(
            request_id=data.get("request_id", ""),
            task_id=data.get("task_id", ""),
            agent_role=data.get("agent_role", ""),
            fields=fields,
            context=data.get("context", ""),
            priority=int(data.get("priority", 1)),
            timeout_seconds=int(data.get("timeout_seconds", 120)),
        )


@dataclass
class ClarificationResponse:
    request_id: str
    answers: dict[str, Any]  # field question -> answer
    skipped: bool = False  # True if user hit Esc or timed out


# Event type string constants (used with Event.type when value is these)
CLARIFICATION_NEEDED = "clarification_needed"
CLARIFICATION_RECEIVED = "clarification_received"
