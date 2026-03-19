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
import queue
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from devsper.types.task import Task, TaskStatus
from devsper.types.event import Event, events
from devsper.utils.event_logger import EventLog
from devsper.events import ClarificationRequest, ClarificationResponse

from devsper.agents.agent import Agent
from devsper.swarm.scheduler import Scheduler
from devsper.swarm.planner import Planner
from devsper.intelligence.adaptation import create_alternative_subtasks_for_failed

if TYPE_CHECKING:
    from devsper.agents.critic import CriticAgent
    from devsper.swarm.prefetcher import TaskPrefetcher


def _get_tools_for_task(task: Task) -> list:
    """Get tools that would be selected for this task (for complexity routing)."""
    try:
        from devsper.tools.selector import get_tools_for_task as _get_tools
        from devsper.tools.scoring import get_default_score_store
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
        sandbox_config: object = None,
        audit_logger: object = None,
        hitl_enabled: bool = False,
        hitl_escalation_checker: object = None,
        hitl_approval_store: object = None,
        hitl_notifier: object = None,
        hitl_resolver: object = None,
        clarification_bus: queue.Queue | None = None,
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
        self.sandbox_config = sandbox_config
        self.audit_logger = audit_logger
        self.hitl_enabled = hitl_enabled
        self.hitl_escalation_checker = hitl_escalation_checker
        self.hitl_approval_store = hitl_approval_store
        self.hitl_notifier = hitl_notifier
        self.hitl_resolver = hitl_resolver
        self.clarification_bus = clarification_bus  # sync queue for TUI to read requests
        self._pending_clarification_queues: dict[str, tuple[queue.Queue, str]] = {}  # request_id -> (response_queue, task_id)
        self._pending_clarification_lock = threading.Lock()

    def request_clarification(self, req: ClarificationRequest) -> ClarificationResponse:
        """
        Called from agent thread. Puts request on clarification_bus, blocks until
        TUI sends response via receive_clarification() or timeout. Returns ClarificationResponse.
        """
        if self.clarification_bus is None:
            return ClarificationResponse(
                request_id=req.request_id,
                answers={},
                skipped=True,
            )
        response_queue: queue.Queue = queue.Queue()
        with self._pending_clarification_lock:
            self._pending_clarification_queues[req.request_id] = (response_queue, req.task_id)
        try:
            self.scheduler.set_task_status(req.task_id, TaskStatus.WAITING_FOR_INPUT)
            self.clarification_bus.put(req)
            try:
                response = response_queue.get(timeout=req.timeout_seconds)
            except queue.Empty:
                response = ClarificationResponse(
                    request_id=req.request_id,
                    answers={},
                    skipped=True,
                )
        finally:
            with self._pending_clarification_lock:
                self._pending_clarification_queues.pop(req.request_id, None)
            self.scheduler.set_task_status(req.task_id, TaskStatus.RUNNING)
        return response

    def receive_clarification(self, response: ClarificationResponse) -> None:
        """Called by TUI when user completes the clarification widget."""
        with self._pending_clarification_lock:
            entry = self._pending_clarification_queues.get(response.request_id)
        if entry is None:
            return
        response_queue, task_id = entry
        response_queue.put(response)
        self.scheduler.set_task_status(task_id, TaskStatus.RUNNING)

    def run_sync(self) -> None:
        """Run the execution loop to completion (synchronous entry point)."""
        asyncio.run(self.run())

    def _semantic_cache_disabled(self) -> bool:
        return os.environ.get("DEVSPER_DISABLE_SEMANTIC_CACHE", "").strip() == "1"

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
            from devsper.bus.message import create_bus_message
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
        if self.audit_logger is not None and self.scheduler is not None:
            try:
                from devsper.audit.logger import make_audit_record
                run_id = getattr(self.scheduler, "run_id", "") or ""
                rec = make_audit_record(
                    run_id=run_id,
                    task_id=task.id,
                    event_type="TASK_STARTED",
                    actor=run_id,
                    resource=getattr(task, "role", "") or "agent",
                    input_text=task.description or "",
                    output_text="",
                )
                self.audit_logger.log(rec)
            except Exception:
                pass

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
            if self.clarification_bus is not None:
                self.agent.clarification_requester = self
                self.agent.current_task_id = task.id
                self.agent.role = getattr(task, "role", None) or "agent"
            use_sandbox = (
                self.sandbox_config is not None
                and getattr(self.sandbox_config, "enabled", False)
            )
            if use_sandbox:
                from devsper.sandbox.sandbox import AgentSandbox, get_quota_for_role
                request = self.agent.build_request(
                    task, model_override=model_override, prefetch_result=prefetch_result
                )
                quota = get_quota_for_role(self.sandbox_config, getattr(task, "role", None))
                sandbox = AgentSandbox(self.agent)
                response = await loop.run_in_executor(
                    None,
                    lambda: sandbox.run(request, quota),
                )
                self.agent.apply_response(task, response)
            else:
                await loop.run_in_executor(
                    None,
                    lambda t=task, m=model_override, p=prefetch_result: self.agent.run_task(
                        t, model_override=m, prefetch_result=p
                    ),
                )
        except Exception as err:
            if self.audit_logger is not None and self.scheduler is not None:
                try:
                    from devsper.audit.logger import make_audit_record
                    run_id = getattr(self.scheduler, "run_id", "") or ""
                    rec = make_audit_record(
                        run_id=run_id,
                        task_id=task.id,
                        event_type="TASK_FAILED",
                        actor=run_id,
                        resource="",
                        input_text=task.description or "",
                        output_text=str(err),
                        success=False,
                    )
                    self.audit_logger.log(rec)
                except Exception:
                    pass
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

        last_critic_score: float | None = None
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
            from devsper.agents.critic import CriticAgent

            critique = await self.critic_agent.critique(
                task, result, model=self.fast_model
            )
            last_critic_score = critique.score
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

        # v2.1: HITL — if escalation triggered, create approval request and wait
        if not is_speculative and self.hitl_enabled and self.hitl_escalation_checker:
            from devsper.agents.agent import AgentResponse
            from devsper.explainability.decision_tree import DecisionRecord
            from devsper.hitl.escalation import EscalationTrigger
            from devsper.hitl.approval import ApprovalRequest, ApprovalStore
            from datetime import timedelta

            fake_response = AgentResponse(
                task_id=task.id,
                result=result,
                tools_called=getattr(task, "tools_called", []) or [],
                broadcasts=[],
                tokens_used=None,
                duration_seconds=0.0,
                error=None,
                success=True,
            )
            fake_decision = DecisionRecord(
                task_id=task.id,
                task_description=task.description or "",
                strategy_selected="",
                strategy_reason="",
                critic_score=last_critic_score,
                confidence=float(last_critic_score) if last_critic_score is not None else 0.0,
            )
            match = self.hitl_escalation_checker.evaluate(task, fake_response, fake_decision)
            if match is not None:
                trigger, hitl_policy = match
                request_id = str(__import__("uuid").uuid4())
                now = datetime.now(timezone.utc)
                timeout_sec = getattr(hitl_policy, "timeout_seconds", 3600)
                expires = now + timedelta(seconds=timeout_sec)
                approval = ApprovalRequest(
                    request_id=request_id,
                    task=task,
                    proposed_result=result,
                    decision_record=fake_decision,
                    trigger=trigger,
                    created_at=now.isoformat(),
                    expires_at=expires.isoformat(),
                    status="pending",
                )
                store = self.hitl_approval_store
                if store is not None:
                    store.save(approval)
                if self.hitl_notifier is not None:
                    await self.hitl_notifier.notify(approval, hitl_policy)
                # In-process resolver or poll store
                approved_result = True
                if self.hitl_resolver is not None:
                    resolver = self.hitl_resolver
                    try:
                        if asyncio.iscoroutinefunction(resolver):
                            approved_result = await resolver(approval, hitl_policy)
                        else:
                            approved_result = await asyncio.to_thread(resolver, approval, hitl_policy)
                    except Exception:
                        approved_result = False
                    if store is not None:
                        store.resolve(request_id, approved_result, "")
                    if not approved_result:
                        self.scheduler.mark_failed(task.id, "Rejected by human reviewer")
                        self._emit(
                            events.TASK_REJECTED_BY_HUMAN,
                            {"task_id": task.id, "request_id": request_id},
                        )
                        return task.id
                    # approved: fall through to mark_completed
                else:
                    # Poll for resolution every 5s up to timeout
                    poll_interval = 5
                    elapsed = 0
                    while store is not None and elapsed < timeout_sec:
                        await asyncio.sleep(min(poll_interval, timeout_sec - elapsed))
                        elapsed += poll_interval
                        req = store.get(request_id)
                        if req is None:
                            break
                        if req.status == "approved":
                            break
                        if req.status == "rejected":
                            self.scheduler.mark_failed(task.id, "Rejected by human reviewer")
                            self._emit(
                                events.TASK_REJECTED_BY_HUMAN,
                                {"task_id": task.id, "request_id": request_id},
                            )
                            return task.id
                    # After loop: approved or timeout
                    req = store.get(request_id) if store else None
                    if req is not None and req.status == "rejected":
                        self.scheduler.mark_failed(task.id, "Rejected by human reviewer")
                        self._emit(
                            events.TASK_REJECTED_BY_HUMAN,
                            {"task_id": task.id, "request_id": request_id},
                        )
                        return task.id
                    if req is not None and req.status == "pending" and elapsed >= timeout_sec:
                        on_timeout = getattr(hitl_policy, "on_timeout", "auto_approve")
                        if on_timeout == "auto_reject":
                            self.scheduler.mark_failed(task.id, "Approval timeout (auto_reject)")
                            if store:
                                approval.status = "timeout"
                                store.save(approval)
                            return task.id
                        # auto_approve or escalate_further: treat as approve for now
                    # approved or auto_approve: fall through to mark_completed

        if not is_speculative:
            self.scheduler.mark_completed(task.id, result)
            self.scheduler.confirm_speculative_for(task.id)
            if self.checkpointer is not None:
                self.checkpointer.on_task_completed(self.scheduler)
            if self.audit_logger is not None and self.scheduler is not None:
                try:
                    from devsper.audit.logger import make_audit_record
                    run_id = getattr(self.scheduler, "run_id", "") or ""
                    rec = make_audit_record(
                        run_id=run_id,
                        task_id=task.id,
                        event_type="TASK_COMPLETED",
                        actor=run_id,
                        resource=getattr(task, "role", "") or "agent",
                        input_text=task.description or "",
                        output_text=(result or "")[:5000],
                        duration_ms=int((task.result and 0) or 0),
                        success=True,
                    )
                    self.audit_logger.log(rec)
                except Exception:
                    pass
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