"""
A2A (Agent-to-Agent) integration: client, server, tool adapter.
"""

from hivemind.agents.a2a.types import (
    AgentCard,
    AgentSkill,
    A2ATaskRequest,
    A2ATaskResponse,
)
from hivemind.agents.a2a.client import A2AClient
from hivemind.agents.a2a.server import create_a2a_app, run_a2a_server
from hivemind.agents.a2a.tool_adapter import A2AAgentTool

# Alias for task spec: "A2AServer" = run_a2a_server / create_a2a_app
A2AServer = create_a2a_app

__all__ = [
    "A2AClient",
    "A2AServer",
    "AgentCard",
    "A2ATaskRequest",
    "A2ATaskResponse",
    "A2AAgentTool",
    "create_a2a_app",
    "run_a2a_server",
]
