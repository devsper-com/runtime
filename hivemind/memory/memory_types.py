"""
Structured memory types for the swarm.

Each memory record has: id, timestamp, source_task, content, tags, embedding (optional).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Kind of memory for routing and indexing."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    ARTIFACT = "artifact"
    RESEARCH = "research"


class MemoryRecord(BaseModel):
    """Single memory entry with optional embedding."""

    id: str
    memory_type: MemoryType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_task: str = ""
    content: str
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    run_id: str = ""  # v1.8: which swarm run produced this (for cross-run synthesis)
    archived: bool = False  # v1.8: consolidated into a summary record

    def to_store_row(self) -> dict[str, Any]:
        """Serialize for storage (embedding as JSON list or null)."""
        return {
            "memory_id": self.id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "tags": ",".join(self.tags) if self.tags else "",
            "timestamp": self.timestamp.isoformat(),
            "source_task": self.source_task,
            "embedding": self.embedding,
            "run_id": getattr(self, "run_id", "") or "",
            "archived": 1 if getattr(self, "archived", False) else 0,
        }


EpisodicMemory = MemoryRecord
SemanticMemory = MemoryRecord
ArtifactMemory = MemoryRecord
ResearchMemory = MemoryRecord
