"""
Executor: runtime engine that runs tasks via agents while respecting scheduler dependencies.

Lifecycle: EXECUTOR_STARTED → (agent/task events per task) → EXECUTOR_FINISHED.
Uses asyncio and a worker pool (Semaphore) to run up to worker_count tasks concurrently.
Supports speculative execution and task cache lookup.
"""

import asyncio
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog

from hivemind.agents.agent import Agent
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.planner import Planner
from hivemind.intelligence.adaptation import create_alternative_subtasks_for_failed


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
        speculative_execution: bool = False,
        task_cache: object = None,
    ) -> None:
        self.scheduler = scheduler
        self.agent = agent
        self.worker_count = worker_count
        self.event_log = event_log or EventLog()
        self.planner = planner
        self.adaptive = adaptive
        self.speculative_execution = speculative_execution
        self.task_cache = task_cache

    def run_sync(self) -> None:
        """Run the execution loop to completion (synchronous entry point)."""
        asyncio.run(self.run())

    def _get_cached_result(self, task: Task) -> str | None:
        """Return cached result if cache is enabled and hit; else None."""
        if self.task_cache is None:
            return None
        try:
            return self.task_cache.get(task)
        except Exception:
            return None

    def _set_cached_result(self, task: Task, result: str) -> None:
        """Store result in cache if cache is enabled."""
        if self.task_cache is None:
            return
        try:
            self.task_cache.set(task, result)
        except Exception:
            pass

    async def run(self) -> None:
        """Run the execution loop until all tasks are completed."""
        self._emit(events.EXECUTOR_STARTED, {})

        sem = asyncio.Semaphore(self.worker_count)
        loop = asyncio.get_running_loop()

        while not self.scheduler.is_finished():
            ready = self.scheduler.get_ready_tasks()
            speculative: list[Task] = []
            if self.speculative_execution:
                speculative = self.scheduler.get_speculative_tasks()

            if not ready and not speculative:
                await asyncio.sleep(0.01)
                continue

            for task in ready:
                task.status = TaskStatus.RUNNING
            for task in speculative:
                task.status = TaskStatus.RUNNING

            async def _execute_task(task: Task, is_speculative: bool) -> None:
                async with sem:
                    cached = self._get_cached_result(task)
                    if cached is not None:
                        task.result = cached
                        task.status = TaskStatus.COMPLETED
                        if not is_speculative:
                            self.scheduler.mark_completed(task.id)
                            self.scheduler.confirm_speculative_for(task.id)
                        return
                    try:
                        await loop.run_in_executor(
                            None, lambda t=task: self.agent.run(t)
                        )
                    except Exception as err:
                        task.status = TaskStatus.FAILED
                        task.result = f"Error: {type(err).__name__}: {err}"
                        self.scheduler.mark_failed(task.id)
                        if is_speculative:
                            self.scheduler.discard_speculative_for(task.id)
                        else:
                            self._emit(
                                events.TASK_FAILED,
                                {"task_id": task.id, "error": str(err)},
                            )
                            if self.adaptive and self.planner:
                                alt = create_alternative_subtasks_for_failed(
                                    task, self.planner, self.scheduler
                                )
                                if alt:
                                    self.scheduler.add_tasks(alt)
                        return
                    self._set_cached_result(task, task.result or "")
                    if not is_speculative:
                        self.scheduler.mark_completed(task.id)
                        self.scheduler.confirm_speculative_for(task.id)
                        if self.adaptive and self.planner:
                            new_tasks = self.planner.expand_tasks(task)
                            if new_tasks:
                                self.scheduler.add_tasks(new_tasks)

            await asyncio.gather(
                *[_execute_task(t, False) for t in ready],
                *[_execute_task(t, True) for t in speculative],
            )

        self._emit(events.EXECUTOR_FINISHED, {})

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(
                timestamp=datetime.now(timezone.utc), type=event_type, payload=payload
            )
        )
