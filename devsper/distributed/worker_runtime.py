from __future__ import annotations

from dataclasses import dataclass

from devsper.agents.agent import Agent
from devsper.runtime.agent_pool import AgentPool
from devsper.runtime.executor import Executor
from devsper.runtime.model_router import ModelRouter
from devsper.runtime.tool_runner import ToolRunner
from devsper.swarm.scheduler import Scheduler
from devsper.utils.event_logger import EventLog


@dataclass
class WorkerRuntime:
    """Worker-local runtime for agent/tool execution."""

    scheduler: Scheduler
    agent: Agent
    event_log: EventLog
    worker_id: str = "worker-local"
    max_agents: int = 4
    tool_concurrency: int = 4

    def __post_init__(self) -> None:
        self.agent_pool = AgentPool(lambda: self.agent, max_agents=self.max_agents)
        self.model_router = ModelRouter(
            planning_model=getattr(self.agent, "model_name", "mock"),
            reasoning_model=getattr(self.agent, "model_name", "mock"),
            validation_model=getattr(self.agent, "model_name", "mock"),
        )
        self.tool_runner = ToolRunner(parallelism=self.tool_concurrency)
        self.executor = Executor(
            scheduler=self.scheduler,
            agent=self.agent,
            event_log=self.event_log,
            worker_count=self.max_agents,
        )

    async def run_task_queue(self) -> dict[str, str]:
        await self.executor.run()
        return self.scheduler.get_results()

