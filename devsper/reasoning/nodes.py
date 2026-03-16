"""
Reasoning node: single artifact produced by an agent during a step.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ReasoningNode(BaseModel):
    """A single reasoning artifact produced by an agent."""

    id: str
    agent_id: str = ""
    task_id: str = ""
    content: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dependencies: list[str] = Field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.id)
