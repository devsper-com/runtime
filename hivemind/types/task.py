import hashlib
import json
from enum import Enum
from pydantic import BaseModel


class TaskStatus(Enum):
    PENDING = 0
    RUNNING = 1
    COMPLETED = 2
    FAILED = -1


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

    def to_dict(self) -> dict:
        """Return all fields as JSON-safe dict."""
        return {
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
                "0": TaskStatus.PENDING,
                "1": TaskStatus.RUNNING,
                "2": TaskStatus.COMPLETED,
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
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "Task":
        return cls.from_dict(json.loads(raw))

    def checksum(self) -> str:
        """SHA256 of to_json(); used to detect state drift between nodes."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
