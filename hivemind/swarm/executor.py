"""
Executor: runtime engine that runs tasks via agents while respecting scheduler dependencies.

Lifecycle: EXECUTOR_STARTED → (agent/task events per task) → EXECUTOR_FINISHED.
Uses asyncio and a worker pool (Semaphore) to run up to worker_count tasks concurrently.
Supports speculative execution and task cache lookup.

v1.6: Semantic task cache, model complexity routing, streaming DAG unblocking.
v1.7: Critic loop, speculative prefetching.
v1.9: Stateless — no task state stored in executor; all state in Scheduler. Publishes to bus.
"""

import os
import asyncio
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog

from hivemind.agents.agent import Agent
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.planner import Planner
from hivemind.intelligence.adaptation import create_alternative_subtasks_for_failed

if TYPE_CHECKING:
    from hivemind.agents.critic import CriticAgent
    from hivemind.swarm.prefetcher import TaskPrefetcher


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
        critic_agent: "CriticAgent | None" = None,
        critic_enabled: bool = False,
        critic_roles: list[str] | None = None,
        fast_model: str = "mock",
        prefetcher: "TaskPrefetcher | None" = None,
        bus: object = None,
        checkpointer: object = None,
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
        self.critic_agent = critic_agent
        self.critic_enabled = critic_enabled
        self.critic_roles = critic_roles or []
        self.fast_model = fast_model
        self.prefetcher = prefetcher
        self.bus = bus
        self.checkpointer = checkpointer

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

    def _publish_bus(self, topic: str, payload: dict) -> None:
        """Publish to bus if configured. Fire-and-forget."""
        if self.bus is None:
            return
        try:
            from hivemind.bus.message import create_bus_message
            run_id = getattr(self.scheduler, "run_id", "") or ""
            msg = create_bus_message(topic=topic, payload=payload, run_id=run_id)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.bus.publish(msg))
            except RuntimeError:
                asyncio.run(self.bus.publish(msg))
        except Exception:
            pass

    async def _execute_task(self, task: Task, is_speculative: bool) -> str:
        """Run one task (cache lookup, agent run, cache store). Returns task.id. No state stored on self."""
        loop = asyncio.get_running_loop()
        cached, hit_info = self._get_cached_result(task)
        if cached is not None:
            if not is_speculative:
                self.scheduler.mark_completed(task.id, cached)
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

        self._publish_bus("task.started", task.to_dict())

        prefetch_result = None
        if self.prefetcher:
            prefetch_result = self.prefetcher.consume(task.id)
            if prefetch_result is not None:
                age_seconds = (
                    datetime.now(timezone.utc) - prefetch_result.computed_at
                ).total_seconds()
                self._emit(
                    events.PREFETCH_HIT,
                    {"task_id": task.id, "age_seconds": round(age_seconds, 2)},
                )
            else:
                self._emit(
                    events.PREFETCH_MISS,
                    {"task_id": task.id, "reason": "stale_or_missing"},
                )

        model_override = None
        if self.complexity_router and self.models_config:
            model_override = self._model_for_task(task)
        try:
            await loop.run_in_executor(
                None,
                lambda t=task, m=model_override, p=prefetch_result: self.agent.run_task(
                    t, model_override=m, prefetch_result=p
                ),
            )
        except Exception as err:
            self.scheduler.mark_failed(task.id, str(err))
            if is_speculative:
                self.scheduler.discard_speculative_for(task.id)
            else:
                self._emit(
                    events.TASK_FAILED,
                    {"task_id": task.id, "error": str(err)},
                )
                self._publish_bus("task.failed", {"task_id": task.id, "error": str(err)})
                if self.adaptive and self.planner:
                    alt = create_alternative_subtasks_for_failed(
                        task, self.planner, self.scheduler
                    )
                    if alt:
                        self.scheduler.add_tasks(alt)
            return task.id

        result = task.result or ""
        self._set_cached_result(task, result)

        # v1.7: critic loop — only for non-speculative, eligible roles, not already retried
        role = getattr(task, "role", None) or ""
        retry_count = getattr(task, "retry_count", 0)
        if (
            not is_speculative
            and self.critic_enabled
            and self.critic_agent
            and role in self.critic_roles
            and retry_count < 1
        ):
            from hivemind.agents.critic import CriticAgent

            critique = await self.critic_agent.critique(
                task, result, model=self.fast_model
            )
            self._emit(
                events.TASK_CRITIQUED,
                {
                    "task_id": task.id,
                    "score": critique.score,
                    "issues": critique.issues,
                    "retry_requested": critique.retry,
                },
            )
            if critique.retry and retry_count < 1:
                retry_prompt = await self.critic_agent.get_retry_prompt(
                    task, result, critique
                )
                task.description = retry_prompt
                task.retry_count = retry_count + 1
                task.result = None
                task.status = TaskStatus.PENDING
                return await self._execute_task(task, is_speculative)

        if not is_speculative:
            self.scheduler.mark_completed(task.id, result)
            self.scheduler.confirm_speculative_for(task.id)
            if self.checkpointer is not None:
                self.checkpointer.on_task_completed(self.scheduler)
            self._publish_bus(
                "task.completed",
                {
                    "task_id": task.id,
                    "result": result,
                    "tokens_used": None,
                    "duration_seconds": 0.0,
                },
            )
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
                if self.prefetcher:
                    for t in speculative:
                        if t.id not in running:
                            asyncio.create_task(self.prefetcher.prefetch(t))

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