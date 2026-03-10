"""
A2AAgentTool: wrap an external A2A agent skill as a hivemind Tool.
"""

import asyncio
import uuid

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

from hivemind.agents.a2a.types import AgentCard, AgentSkill, A2ATaskRequest, A2ATaskResponse
from hivemind.agents.a2a.client import A2AClient


class A2AAgentTool(Tool):
    """
    Wraps an external A2A agent skill as a hivemind tool.
    Discovery: fetch AgentCard, create one tool per skill.
    """

    def __init__(
        self,
        agent_name: str,
        skill: AgentSkill,
        base_url: str,
        client: A2AClient | None = None,
    ) -> None:
        self.name = f"{agent_name}.{skill.id}"
        self.description = skill.description or f"A2A skill: {skill.name}"
        self.category = "a2a"
        self.input_schema = {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "Task or prompt for the agent"}},
            "required": ["task"],
        }
        self._base_url = base_url.rstrip("/")
        self._client = client or A2AClient()
        self._skill_id = skill.id
        register(self)

    def run(self, task: str = "", **kwargs) -> str:
        """Send task to external A2A agent via send_task."""
        text = task or kwargs.get("task", "")
        if not text:
            return "Error: missing 'task' argument"
        request = A2ATaskRequest(
            id=str(uuid.uuid4()),
            message={"text": text},
            session_id=None,
        )
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self._client.send_task(self._base_url, request),
                )
                resp = future.result()
        else:
            resp = loop.run_until_complete(self._client.send_task(self._base_url, request))
        if resp.status == "completed" and resp.result is not None:
            return resp.result
        return f"Error: status={resp.status}, result={resp.result}"
