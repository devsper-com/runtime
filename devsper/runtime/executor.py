"""Runtime-native executor with event-driven orchestration."""

from __future__ import annotations

import asyncio
import uuid
import threading
from dataclasses import dataclass

from devsper.agents.agent import Agent
from devsper.runtime.agent_pool import AgentPool
from devsper.runtime.agent_runner import AgentRunner
from devsper.runtime.execution_graph import ExecutionGraph
from devsper.runtime.event_stream import RuntimeEventStream
from devsper.runtime.hitl import HITLManager, HITLRequest
from devsper.runtime.model_router import ModelRouter
from devsper.runtime.planner import RuntimePlanner
from devsper.runtime.retry import RetryConfig, RetryPolicy
from devsper.runtime.speculative_planner import SpeculativePlanner
from devsper.runtime.state_manager import RuntimeStateManager
from devsper.runtime.task_runner import TaskRunner
from devsper.swarm.planner import Planner
from devsper.swarm.scheduler import Scheduler
from devsper.types.event import events
from devsper.utils.event_logger import EventLog


@dataclass
class RuntimeResources:
    worker_count: int = 4
    poll_interval_seconds: float = 0.02
    max_running_queue: int = 4096


class Executor:
    """Runs ready tasks concurrently with cancellation and retries."""

    def __init__(
        self,
        scheduler: Scheduler,
        agent: Agent,
        worker_count: int = 4,
        event_log: EventLog | None = None,
        pause_event: threading.Event | None = None,
        fast_model: str = "mock",
        planner: Planner | None = None,
        adaptive: bool = False,
        streaming_dag: bool = True,
        parallel_tools: bool = True,
        cancellation_event: threading.Event | None = None,
        max_running_queue: int = 4096,
        worker_id: str = "controller-local",
        agent_pool_size: int = 4,
        enable_speculative: bool = False,
        enable_hitl: bool = False,
        **_: object,
    ) -> None:
        self.scheduler = scheduler
        self.agent = agent
        self.resources = RuntimeResources(
            worker_count=max(1, int(worker_count)),
            max_running_queue=max(1, int(max_running_queue)),
        )
        self.pause_event = pause_event
        self._cancel_event = cancellation_event or threading.Event()
        self._adaptive = bool(adaptive)
        self._streaming_dag = bool(streaming_dag)
        self._worker_id = worker_id
        self._enable_speculative = bool(enable_speculative)
        self._hitl = HITLManager() if enable_hitl else None
        self._dynamic_planner = RuntimePlanner(planner if self._adaptive else None)
        self._speculative_planner = SpeculativePlanner(max_predictions=2)
        self.event_stream = RuntimeEventStream(event_log or EventLog())
        self.state = RuntimeStateManager(scheduler)
        self.execution_graph = ExecutionGraph()
        self._running_limit_sem = asyncio.Semaphore(self.resources.max_running_queue)
        self.model_router = ModelRouter(
            planning_model=getattr(agent, "model_name", "mock"),
            reasoning_model=getattr(agent, "model_name", "mock"),
            validation_model=getattr(agent, "model_name", "mock"),
        )
        self.agent_pool = AgentPool(
            agent_factory=lambda: agent,
            max_agents=max(1, int(agent_pool_size)),
            streaming_tools=bool(
                parallel_tools
                and str(__import__("os").environ.get("DEVSPER_STREAMING_TOOL_INVOCATION", "0")).strip()
                in ("1", "true", "True")
            ),
        )
        self.task_runner = TaskRunner(
            agent_runner=AgentRunner(
                agent,
                streaming_tools=False,
            ),
            agent_pool=self.agent_pool,
            model_router=self.model_router,
            retry_policy=RetryPolicy(max_attempts=2),
            retry_config=RetryConfig(),
            fallback_model=fast_model,
        )
        for task in self.scheduler.get_all_tasks():
            self.execution_graph.add_task(task)

    def cancel(self) -> None:
        self._cancel_event.set()

    def run_sync(self) -> None:
        asyncio.run(self.run())

    async def run(self) -> None:
        await self.event_stream.publish(events.EXECUTOR_STARTED, {})
        sem = asyncio.Semaphore(self.resources.worker_count)
        running: dict[str, asyncio.Task] = {}

        async def _run_one(task_id: str):
            async with sem:
                async with self._running_limit_sem:
                    task = self.scheduler.get_task(task_id)
                    self.execution_graph.assign_worker(task.id, self._worker_id)
                    self.execution_graph.mark_running(task.id, worker_id=self._worker_id)
                    if self._hitl is not None and self._hitl.is_paused(task.id):
                        await asyncio.sleep(self.resources.poll_interval_seconds)
                        return
                    await self.event_stream.publish(events.TASK_STARTED, {"task_id": task.id})
                    result = await self.task_runner.run(task, worker_id=self._worker_id)
                    if result.success:
                        self.state.mark_completed(task.id, result.output)
                        self.execution_graph.mark_completed(task.id)
                        await self.event_stream.publish(events.TASK_COMPLETED, {"task_id": task.id})
                        batch = self._dynamic_planner.expand(task)
                        if batch is not None and batch.tasks:
                            self.state.add_tasks(batch.tasks)
                            for created in batch.tasks:
                                self.execution_graph.add_task(created, lineage_root=batch.parent_task_id)
                                await self.event_stream.publish(
                                    events.TASK_CREATED,
                                    {
                                        "task_id": created.id,
                                        "description": created.description,
                                        "lineage_parent": batch.parent_task_id,
                                    },
                                )
                        if self._enable_speculative:
                            speculative = self._speculative_planner.predict_next(task, self.scheduler)
                            if speculative is not None and speculative.predicted_tasks:
                                for predicted in speculative.predicted_tasks:
                                    await self.event_stream.publish(
                                        events.TASK_CREATED,
                                        {
                                            "task_id": predicted.id,
                                            "description": predicted.description,
                                            "speculative": True,
                                            "lineage_parent": speculative.parent_task_id,
                                        },
                                    )
                    else:
                        err = result.error or "Task execution failed"
                        if self._hitl is not None and "Human-in-the-Loop required" in err:
                            req = HITLRequest(
                                request_id=str(uuid.uuid4()),
                                task_id=task.id,
                                prompt=err,
                                timeout_seconds=120,
                            )
                            await self._hitl.pause_task(task.id)
                            await self.event_stream.publish(events.CLARIFICATION_REQUESTED, self._hitl.event_payload(req))
                        self.state.mark_failed(task.id, err)
                        self.execution_graph.mark_failed(task.id)
                        if self._enable_speculative:
                            _ = self._speculative_planner.cancel_unused(task.id, self.scheduler)
                        await self.event_stream.publish(
                            events.TASK_FAILED,
                            {"task_id": task.id, "error": err},
                        )

        while not self.state.is_finished() and not self._cancel_event.is_set():
            if self.pause_event is not None and not self.pause_event.is_set():
                await asyncio.sleep(self.resources.poll_interval_seconds)
                continue

            slots = self.resources.worker_count - len(running)
            if slots > 0:
                ready = self.state.next_ready_tasks(slots)
                for task in ready:
                    running[task.id] = asyncio.create_task(_run_one(task.id))

            if not running:
                await asyncio.sleep(self.resources.poll_interval_seconds)
                continue

            done, _pending = await asyncio.wait(
                list(running.values()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            done_ids = {tid for tid, fut in running.items() if fut in done}
            for tid in done_ids:
                fut = running.pop(tid)
                await fut

        if self._cancel_event.is_set():
            for fut in list(running.values()):
                fut.cancel()
            if running:
                await asyncio.gather(*running.values(), return_exceptions=True)
        await self.event_stream.publish(events.EXECUTOR_FINISHED, {})
        await self.event_stream.publish(events.RUN_COMPLETED, {})


__all__ = ["Executor"]
