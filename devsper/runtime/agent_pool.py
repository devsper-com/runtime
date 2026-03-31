from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Callable

from devsper.agents.agent import Agent
from devsper.runtime.agent_runner import AgentRunner
from devsper.types.task import Task


@dataclass(frozen=True)
class AgentLease:
    worker_id: str
    agent: Agent


class AgentPool:
    """Reusable async pool for worker-local agent execution."""

    def __init__(
        self,
        agent_factory: Callable[[], Agent],
        max_agents: int = 8,
        streaming_tools: bool = False,
    ) -> None:
        self._factory = agent_factory
        self._max_agents = max(1, int(max_agents))
        self._streaming_tools = bool(streaming_tools)
        self._queues: dict[str, asyncio.Queue[Agent]] = defaultdict(asyncio.Queue)
        self._created: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire_agent(self, worker_id: str = "default") -> AgentLease:
        queue = self._queues[worker_id]
        try:
            agent = queue.get_nowait()
            return AgentLease(worker_id=worker_id, agent=agent)
        except asyncio.QueueEmpty:
            pass

        async with self._lock:
            if self._created[worker_id] < self._max_agents:
                self._created[worker_id] += 1
                return AgentLease(worker_id=worker_id, agent=self._factory())

        agent = await queue.get()
        return AgentLease(worker_id=worker_id, agent=agent)

    async def release_agent(self, lease: AgentLease) -> None:
        await self._queues[lease.worker_id].put(lease.agent)

    async def run_agent(
        self,
        task: Task,
        worker_id: str = "default",
        model_override: str | None = None,
    ) -> str:
        lease = await self.acquire_agent(worker_id=worker_id)
        try:
            runner = AgentRunner(lease.agent, streaming_tools=self._streaming_tools)
            return await runner.run_task(task, model_override=model_override)
        finally:
            await self.release_agent(lease)

    async def run_parallel(
        self,
        tasks: list[Task],
        worker_id: str = "default",
        model_override: str | None = None,
    ) -> list[str]:
        return await asyncio.gather(
            *(self.run_agent(t, worker_id=worker_id, model_override=model_override) for t in tasks)
        )

    @asynccontextmanager
    async def lease(self, worker_id: str = "default"):
        lease = await self.acquire_agent(worker_id=worker_id)
        try:
            yield lease.agent
        finally:
            await self.release_agent(lease)

