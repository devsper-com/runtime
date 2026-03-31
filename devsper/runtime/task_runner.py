from __future__ import annotations

import os
from dataclasses import dataclass

from devsper.runtime.agent_runner import AgentRunner
from devsper.runtime.agent_pool import AgentPool
from devsper.runtime.model_router import ModelRouter
from devsper.runtime.retry import RetryConfig, RetryPolicy, RetryScope, with_retry
from devsper.types.task import Task


@dataclass
class TaskExecutionResult:
    task_id: str
    success: bool
    output: str
    error: str | None = None


class TaskRunner:
    """Executes one task with retries and model fallback."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        agent_pool: AgentPool | None = None,
        model_router: ModelRouter | None = None,
        retry_policy: RetryPolicy | None = None,
        retry_config: RetryConfig | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self._agent_runner = agent_runner
        self._agent_pool = agent_pool
        self._model_router = model_router
        self._retry_policy = retry_policy or RetryPolicy()
        self._retry_config = retry_config or RetryConfig(
            task=self._retry_policy,
            agent=self._retry_policy,
        )
        self._fallback_model = fallback_model

    @staticmethod
    def _debug_enabled() -> bool:
        return str(os.environ.get("DEVSPER_RUNTIME_DEBUG", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    async def run(
        self,
        task: Task,
        model_override: str | None = None,
        worker_id: str = "default",
    ) -> TaskExecutionResult:
        route = self._model_router.route(task) if self._model_router is not None else None
        model = (model_override or (route.primary if route is not None else "") or "").strip()
        if not model:
            model = "mock"

        async def _run_agent(selected_model: str | None) -> str:
            if self._agent_pool is not None:
                return await self._agent_pool.run_agent(
                    task,
                    worker_id=worker_id,
                    model_override=selected_model,
                )
            return await self._agent_runner.run_task(task, model_override=selected_model)

        try:
            if self._debug_enabled():
                print(f"[task-runner] task_id={task.id} selected_model={model}")
            output = await with_retry(
                lambda: _run_agent(model),
                self._retry_config.for_scope(RetryScope.AGENT),
            )
            return TaskExecutionResult(task_id=task.id, success=True, output=output or "", error=None)
        except Exception as exc:
            fallback_models: list[str] = []
            if route is not None:
                fallback_models.extend([m for m in route.fallbacks if m and m != model])
            if self._fallback_model and self._fallback_model != model:
                fallback_models.append(self._fallback_model)
            fallback_errors: list[str] = []
            for fallback in fallback_models:
                try:
                    if self._debug_enabled():
                        print(f"[task-runner] task_id={task.id} fallback_model={fallback}")
                    output = await with_retry(
                        lambda: _run_agent(fallback),
                        self._retry_config.for_scope(RetryScope.MODEL_FALLBACK),
                    )
                    return TaskExecutionResult(task_id=task.id, success=True, output=output or "", error=None)
                except Exception as fallback_exc:
                    fallback_errors.append(f"{fallback}: {type(fallback_exc).__name__}: {fallback_exc}")
                    continue
            details = "; ".join(fallback_errors) if fallback_errors else "none"
            return TaskExecutionResult(
                task_id=task.id,
                success=False,
                output="",
                error=f"{type(exc).__name__}: {exc} | fallback_errors={details}",
            )

