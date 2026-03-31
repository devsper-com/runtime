from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class RetryScope(str, Enum):
    TOOL = "tool"
    AGENT = "agent"
    TASK = "task"
    MODEL_FALLBACK = "model_fallback"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 5.0
    backoff_multiplier: float = 2.0


@dataclass(frozen=True)
class RetryConfig:
    tool: RetryPolicy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.25)
    agent: RetryPolicy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.5)
    task: RetryPolicy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.75)
    model_fallback: RetryPolicy = RetryPolicy(max_attempts=1, initial_delay_seconds=0.0)

    def for_scope(self, scope: RetryScope) -> RetryPolicy:
        if scope == RetryScope.TOOL:
            return self.tool
        if scope == RetryScope.AGENT:
            return self.agent
        if scope == RetryScope.MODEL_FALLBACK:
            return self.model_fallback
        return self.task


async def with_retry(
    op: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    retryable: Callable[[Exception], bool] | None = None,
) -> T:
    attempts = max(1, int(policy.max_attempts))
    delay = max(0.0, float(policy.initial_delay_seconds))
    for i in range(attempts):
        try:
            return await op()
        except Exception as exc:
            if i >= attempts - 1:
                raise
            if retryable is not None and not retryable(exc):
                raise
            await asyncio.sleep(delay)
            delay = min(float(policy.max_delay_seconds), delay * float(policy.backoff_multiplier))
    raise RuntimeError("retry loop terminated unexpectedly")

