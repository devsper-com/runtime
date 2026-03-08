"""
Executor: runtime engine that runs tasks via agents while respecting scheduler dependencies.

Lifecycle: EXECUTOR_STARTED → (agent/task events per task) → EXECUTOR_FINISHED.
Uses asyncio and a worker pool (Semaphore) to run up to worker_count tasks concurrently.
"""

import asyncio
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog

from hivemind.agents.agent import Agent
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.planner import Planner


class Executor:
    """Executes tasks using an agent, respecting the scheduler DAG and worker limit."""

    def __init__(
        self,
        scheduler: Scheduler,
        agent: Agent,
        worker_count: int = 4,
        event_log: EventLog | None = None,
        planner: Planner | None = None,
        adaptive: bool = False,
    ) -> None:
        self.scheduler = scheduler
        self.agent = agent
        self.worker_count = worker_count
        self.event_log = event_log or EventLog()
        self.planner = planner
        self.adaptive = adaptive

    def run_sync(self) -> None:
        """Run the execution loop to completion (synchronous entry point)."""
        asyncio.run(self.run())

    async def run(self) -> None:
        """Run the execution loop until all tasks are completed."""
        self._emit(events.EXECUTOR_STARTED, {})

        sem = asyncio.Semaphore(self.worker_count)
        loop = asyncio.get_running_loop()

        while not self.scheduler.is_finished():
            ready = self.scheduler.get_ready_tasks()
            if not ready:
                await asyncio.sleep(0.01)
                continue

            for task in ready:
                task.status = TaskStatus.RUNNING

            async def _execute_task(task: Task) -> None:
                async with sem:
                    await loop.run_in_executor(None, lambda t=task: self.agent.run(t))
                    self.scheduler.mark_completed(task.id)
                    if self.adaptive and self.planner:
                        new_tasks = self.planner.expand_tasks(task)
                        if new_tasks:
                            self.scheduler.add_tasks(new_tasks)

            await asyncio.gather(*[_execute_task(t) for t in ready])

        self._emit(events.EXECUTOR_FINISHED, {})

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
