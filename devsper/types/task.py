import hashlib
import json
from enum import Enum
from pydantic import BaseModel


class TaskStatus(Enum):
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = -1
    WAITING_FOR_INPUT = 3  # clarification / human input


class Task(BaseModel):
    id: str
    description: str
    dependencies: list[str] = []
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None  # v1.9: error message when failed
    speculative: bool = False
    role: str | None = None  # Optional agent role: research, code, analysis, critic
    retry_count: int = 0  # v1.7: critic retries
    project_id: str | None = None  # platform project scope for memory namespace
    agent: str | None = None  # optional named agent assignment
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    tokens_used: int | None = None
    cost_usd: float | None = None

    def to_dict(self) -> dict:
        """Return all fields as JSON-safe dict."""
        d = {
            "id": self.id,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "result": self.result,
            "error": self.error,
            "speculative": self.speculative,
            "role": self.role,
            "retry_count": self.retry_count,
        }
        if self.project_id:
            d["project_id"] = self.project_id
        if self.agent:
            d["agent"] = self.agent
        if self.prompt_tokens is not None:
            d["prompt_tokens"] = self.prompt_tokens
        if self.completion_tokens is not None:
            d["completion_tokens"] = self.completion_tokens
        if self.tokens_used is not None:
            d["tokens_used"] = self.tokens_used
        if self.cost_usd is not None:
            d["cost_usd"] = self.cost_usd
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Reconstruct Task from dict. Parse status back to TaskStatus enum."""
        status = data.get("status", TaskStatus.PENDING)
        if isinstance(status, int):
            task_status = TaskStatus(status)
        elif isinstance(status, str):
            name_to_status = {
                "PENDING": TaskStatus.PENDING,
                "RUNNING": TaskStatus.RUNNING,
                "COMPLETED": TaskStatus.COMPLETED,
                "FAILED": TaskStatus.FAILED,
                "WAITING_FOR_INPUT": TaskStatus.WAITING_FOR_INPUT,
                "0": TaskStatus.PENDING,
                "1": TaskStatus.RUNNING,
                "2": TaskStatus.COMPLETED,
                "3": TaskStatus.WAITING_FOR_INPUT,
                "-1": TaskStatus.FAILED,
            }
            task_status = name_to_status.get(status.upper(), TaskStatus.PENDING)
        else:
            task_status = TaskStatus.PENDING
        return cls(
            id=data["id"],
            description=data.get("description", ""),
            dependencies=list(data.get("dependencies", [])),
            status=task_status,
            result=data.get("result"),
            error=data.get("error"),
            speculative=data.get("speculative", False),
            role=data.get("role"),
            retry_count=data.get("retry_count", 0),
            project_id=data.get("project_id"),
            agent=data.get("agent"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            tokens_used=data.get("tokens_used"),
            cost_usd=data.get("cost_usd"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "Task":
        return cls.from_dict(json.loads(raw))

    def checksum(self) -> str:
        """SHA256 of to_json(); used to detect state drift between nodes."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
