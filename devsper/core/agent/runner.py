from __future__ import annotations

from devsper.agents.agent import Agent, AgentRequest, AgentResponse


class AgentRuntimeAdapter:
    """Compatibility facade so legacy Agent can be wired through core layer."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    def run(self, request: AgentRequest) -> AgentResponse:
        return self._agent.run(request)

