"""
A2A client: call external A2A-compliant agents (get AgentCard, send_task, stream_task).
"""

import uuid
from typing import AsyncIterator

from devsper.agents.a2a.types import (
    AgentCard,
    AgentSkill,
    A2ATaskRequest,
    A2ATaskResponse,
)


def _parse_agent_card(data: dict) -> AgentCard:
    """Build AgentCard from JSON response."""
    skills_data = data.get("skills") or []
    skills = [
        AgentSkill(
            id=s.get("id", ""),
            name=s.get("name", ""),
            description=s.get("description", ""),
            input_modes=list(s.get("inputModes") or []),
            output_modes=list(s.get("outputModes") or []),
        )
        for s in skills_data
        if isinstance(s, dict)
    ]
    return AgentCard(
        name=data.get("name", ""),
        description=data.get("description", ""),
        url=data.get("url", ""),
        version=data.get("version", ""),
        capabilities=list(data.get("capabilities") or []),
        skills=skills,
        authentication=data.get("authentication"),
    )


def _parse_task_response(data: dict) -> A2ATaskResponse:
    """Build A2ATaskResponse from JSON."""
    status = data.get("status", "failed")
    if status not in ("submitted", "working", "completed", "failed", "canceled"):
        status = "failed"
    return A2ATaskResponse(
        id=data.get("id", ""),
        status=status,
        result=data.get("result"),
        artifacts=data.get("artifacts") or [],
    )


class A2AClient:
    """Calls external A2A-compliant agents as if they were local tools."""

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    def _client(self):
        import httpx
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    async def get_agent_card(self, base_url: str) -> AgentCard:
        """GET {base_url}/.well-known/agent.json"""
        url = base_url.rstrip("/") + "/.well-known/agent.json"
        async with self._client() as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        return _parse_agent_card(data)

    async def send_task(
        self,
        base_url: str,
        request: A2ATaskRequest,
        poll_interval: float = 0.5,
    ) -> A2ATaskResponse:
        """POST {base_url}/tasks/send, then poll GET /tasks/{id} until completed/failed."""
        import asyncio
        url = base_url.rstrip("/") + "/tasks/send"
        body = {
            "id": request.id,
            "message": request.message,
            "sessionId": request.session_id,
        }
        async with self._client() as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        resp = _parse_task_response(data)
        if resp.status in ("completed", "failed", "canceled"):
            return resp
        task_url = base_url.rstrip("/") + f"/tasks/{resp.id}"
        while resp.status in ("submitted", "working"):
            await asyncio.sleep(poll_interval)
            async with self._client() as client:
                r = await client.get(task_url)
                r.raise_for_status()
                data = r.json()
            resp = _parse_task_response(data)
            if resp.status in ("completed", "failed", "canceled"):
                return resp
        return resp

    async def stream_task(
        self,
        base_url: str,
        request: A2ATaskRequest,
    ) -> AsyncIterator[str]:
        """POST {base_url}/tasks/sendSubscribe, consume SSE stream, yield text chunks."""
        import httpx
        url = base_url.rstrip("/") + "/tasks/sendSubscribe"
        body = {
            "id": request.id,
            "message": request.message,
            "sessionId": request.session_id,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream("POST", url, json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data and data != "[DONE]":
                            yield data
