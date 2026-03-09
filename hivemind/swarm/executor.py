"""
Executor: runtime engine that runs tasks via agents while respecting scheduler dependencies.

Lifecycle: EXECUTOR_STARTED → (agent/task events per task) → EXECUTOR_FINISHED.
Uses asyncio and a worker pool (Semaphore) to run up to worker_count tasks concurrently.
Supports speculative execution and task cache lookup.

v1.6: Semantic task cache, model complexity routing, streaming DAG unblocking.
"""

import os
import asyncio
import threading
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog

from hivemind.agents.agent import Agent
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.planner import Planner
from hivemind.intelligence.adaptation import create_alternative_subtasks_for_failed


def _get_tools_for_task(task: Task) -> list:
    """Get tools that would be selected for this task (for complexity routing)."""
    try:
        from hivemind.tools.selector import get_tools_for_task as _get_tools
        from hivemind.tools.scoring import get_default_score_store
        score_store = get_default_score_store()
    except Exception:
        score_store = None
    return _get_tools(
        task.description or "",
        role=getattr(task, "role", None),
        score_store=score_store,
    )


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
        pause_event: threading.Event | None = None,
        semantic_cache: object = None,
        complexity_router: object = None,
        models_config: object = None,
        streaming_dag: bool = True,
    ) -> None:
        self.scheduler = scheduler
        self.agent = agent
        self.worker_count = worker_count
        self.event_log = event_log or EventLog()
        self.planner = planner
        self.adaptive = adaptive
        self.speculative_execution = speculative_execution
        self.task_cache = task_cache
        self.pause_event = pause_event
        self.semantic_cache = semantic_cache
        self.complexity_router = complexity_router
        self.models_config = models_config or getattr(agent, "model_name", "mock")
        self.streaming_dag = streaming_dag

    def run_sync(self) -> None:
        """Run the execution loop to completion (synchronous entry point)."""
        asyncio.run(self.run())

    def _semantic_cache_disabled(self) -> bool:
        return os.environ.get("HIVEMIND_DISABLE_SEMANTIC_CACHE", "").strip() == "1"

    def _get_cached_result(self, task: Task) -> tuple[str | None, dict | None]:
        """
        Return (cached_result, hit_info). hit_info is None or {similarity, original_description}
        for semantic hits. Uses semantic cache first if enabled, then exact task_cache.
        """
        if self.semantic_cache is not None and not self._semantic_cache_disabled():
            try:
                hit = self.semantic_cache.lookup(task.description or "")
                if hit is not None:
                    return (
                        hit.result,
                        {
                            "similarity": hit.similarity,
                            "original_description": hit.original_description,
                        },
                    )
            except Exception:
                pass
            self._emit(events.TASK_CACHE_MISS, {"task_id": task.id})
        if self.task_cache is None:
            return (None, None)
        try:
            out = self.task_cache.get(task)
            return (out, None) if out is not None else (None, None)
        except Exception:
            return (None, None)

    def _set_cached_result(self, task: Task, result: str) -> None:
        """Store result in exact and/or semantic cache."""
        if self.task_cache is not None:
            try:
                self.task_cache.set(task, result)
            except Exception:
                pass
        if self.semantic_cache is not None and not self._semantic_cache_disabled():
            try:
                self.semantic_cache.store_result(
                    task.description or "",
                    result,
                    getattr(task, "role", None) or "general",
                )
            except Exception:
                pass

    def _model_for_task(self, task: Task) -> str:
        """Return model name for this task (complexity routing or agent default)."""
        if self.complexity_router is None or self.models_config is None:
            return getattr(self.agent, "model_name", "mock")
        tools = _get_tools_for_task(task)
        tier = self.complexity_router.classify(task, tools)
        model = self.complexity_router.select_model(tier, self.models_config)
        self._emit(
            events.TASK_MODEL_SELECTED,
            {"task_id": task.id, "tier": tier, "model": model},
        )
        return model

    async def _execute_task(self, task: Task, is_speculative: bool) -> str:
        """Run one task (cache lookup, agent run, cache store). Returns task.id."""
        loop = asyncio.get_running_loop()
        cached, hit_info = self._get_cached_result(task)
        if cached is not None:
            task.result = cached
            task.status = TaskStatus.COMPLETED
            if not is_speculative:
                self.scheduler.mark_completed(task.id)
                self.scheduler.confirm_speculative_for(task.id)
            if hit_info:
                self._emit(
                    events.TASK_CACHE_HIT,
                    {
                        "task_id": task.id,
                        "similarity": hit_info["similarity"],
                        "original_description": hit_info["original_description"],
                    },
                )
            return task.id
        model_override = None
        if self.complexity_router and self.models_config:
            model_override = self._model_for_task(task)
        try:
            await loop.run_in_executor(
                None,
                lambda t=task, m=model_override: self.agent.run(t, model_override=m),
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
            return task.id
        self._set_cached_result(task, task.result or "")
        if not is_speculative:
            self.scheduler.mark_completed(task.id)
            self.scheduler.confirm_speculative_for(task.id)
            if self.adaptive and self.planner:
                new_tasks = self.planner.expand_tasks(task)
                if new_tasks:
                    self.scheduler.add_tasks(new_tasks)
        return task.id

    async def run(self) -> None:
        """Run the execution loop until all tasks are completed."""
        self._emit(events.EXECUTOR_STARTED, {})

        sem = asyncio.Semaphore(self.worker_count)
        running: dict[str, tuple[Task, bool, asyncio.Task]] = {}  # task_id -> (task, is_speculative, future)

        async def run_with_sem(task: Task, is_spec: bool) -> str:
            async with sem:
                return await self._execute_task(task, is_spec)

        while not self.scheduler.is_finished():
            if self.pause_event is not None and not self.pause_event.is_set():
                await asyncio.sleep(0.2)
                continue

            ready = self.scheduler.get_ready_tasks()
            speculative: list[Task] = []
            if self.speculative_execution:
                speculative = self.scheduler.get_speculative_tasks()

            if self.streaming_dag:
                for task in ready + speculative:
                    if task.id in running:
                        continue
                    if len(running) >= self.worker_count:
                        break
                    task.status = TaskStatus.RUNNING
                    is_spec = task in speculative
                    fut = asyncio.create_task(run_with_sem(task, is_spec))
                    running[task.id] = (task, is_spec, fut)
                if not running:
                    if not ready and not speculative:
                        await asyncio.sleep(0.01)
                    continue
                done, _ = await asyncio.wait(
                    [f for _, _, f in running.values()],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for f in done:
                    try:
                        tid = f.result()
                    except Exception:
                        tid = None
                    if tid and tid in running:
                        del running[tid]
                continue

            for task in ready:
                task.status = TaskStatus.RUNNING
            for task in speculative:
                task.status = TaskStatus.RUNNING
            await asyncio.gather(
                *[run_with_sem(t, False) for t in ready],
                *[run_with_sem(t, True) for t in speculative],
            )

        self._emit(events.EXECUTOR_FINISHED, {})

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(
                timestamp=datetime.now(timezone.utc), type=event_type, payload=payload
            )
        )