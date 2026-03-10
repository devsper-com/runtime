"""
A2A discovery: fetch AgentCard from URL, register skills as A2AAgentTool.
"""

import asyncio

from hivemind.config.schema import A2AAgentConfig
from hivemind.agents.a2a.client import A2AClient
from hivemind.agents.a2a.tool_adapter import A2AAgentTool


async def discover_a2a_tools_async(agent_config: A2AAgentConfig) -> int:
    """Fetch AgentCard from agent URL, create A2AAgentTool per skill, register. Return count."""
    client = A2AClient()
    card = await client.get_agent_card(agent_config.url)
    name = agent_config.name or card.name or "a2a-agent"
    for skill in card.skills:
        A2AAgentTool(agent_name=name, skill=skill, base_url=agent_config.url, client=client)
    return len(card.skills)


def register_a2a_agent(agent_config: A2AAgentConfig) -> int:
    """Sync: discover and register A2A agent tools; return count."""
    return asyncio.run(discover_a2a_tools_async(agent_config))
