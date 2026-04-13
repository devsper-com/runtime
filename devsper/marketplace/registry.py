"""
CapabilityRegistry: stores agent capability vectors.
Agents register themselves with role + tools + system_prompt.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class AgentCapability:
    agent_id: str
    role: str
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    vector: list[float] = field(default_factory=list)
    historical_performance: float = 0.5  # 0.0–1.0, updated after each run
    current_load: float = 0.0            # 0.0–1.0, updated by executor


class CapabilityRegistry:
    """Thread-safe registry of agent capabilities and their vectors."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, AgentCapability] = {}

    def register(self, cap: AgentCapability) -> None:
        """Register or update an agent's capability."""
        from devsper.marketplace.vectors import embed
        if not cap.vector:
            cap.vector = embed(cap.role + " " + " ".join(cap.tools))
        with self._lock:
            self._agents[cap.agent_id] = cap

    def update_performance(self, agent_id: str, score: float) -> None:
        """Update historical performance score (exponential moving average)."""
        with self._lock:
            cap = self._agents.get(agent_id)
            if cap:
                # EMA with alpha=0.3
                cap.historical_performance = 0.7 * cap.historical_performance + 0.3 * score

    def update_load(self, agent_id: str, load: float) -> None:
        with self._lock:
            cap = self._agents.get(agent_id)
            if cap:
                cap.current_load = max(0.0, min(1.0, load))

    def all_agents(self) -> list[AgentCapability]:
        with self._lock:
            return list(self._agents.values())

    def get(self, agent_id: str) -> AgentCapability | None:
        with self._lock:
            return self._agents.get(agent_id)

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)
