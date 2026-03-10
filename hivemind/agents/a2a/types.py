"""
A2A (Agent-to-Agent) protocol types — AgentCard, TaskRequest/Response, etc.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentSkill:
    """One skill exposed by an A2A agent."""
    id: str
    name: str
    description: str
    input_modes: list[str]  # e.g. ["text", "file"]
    output_modes: list[str]


@dataclass
class AgentCard:
    """A2A agent descriptor — follows A2A spec."""
    name: str
    description: str
    url: str  # this agent's A2A endpoint
    version: str
    capabilities: list[str]  # e.g. ["streaming", "pushNotifications"]
    skills: list[AgentSkill]
    authentication: dict | None = None


@dataclass
class A2ATaskRequest:
    """A2A task send request."""
    id: str  # uuid4
    message: dict  # A2A Message object
    session_id: str | None = None


@dataclass
class A2ATaskResponse:
    """A2A task response."""
    id: str
    status: Literal["submitted", "working", "completed", "failed", "canceled"]
    result: str | None = None
    artifacts: list[dict] | None = None

    def __post_init__(self) -> None:
        if self.artifacts is None:
            self.artifacts = []
