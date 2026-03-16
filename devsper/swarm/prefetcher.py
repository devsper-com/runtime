"""
Speculative pre-fetching: pre-warm memory context and tool selection for likely successor tasks.
v1.7.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devsper.tools.base import Tool


@dataclass
class PrefetchResult:
    memory_context: str
    tools: list  # list[Tool]
    computed_at: datetime


class TaskPrefetcher:
    """
    While a task is running, pre-warm its likely successors:
    fetch memory context and select tools in background.
    Results are cached and consumed by the agent when the task actually starts.
    """

    def __init__(
        self,
        memory_router,
        tool_selector,
        score_store=None,
        max_age_seconds: float = 30.0,
    ):
        self._memory_router = memory_router
        self._tool_selector = tool_selector
        self._score_store = score_store
        self._max_age_seconds = max_age_seconds
        self._warmup_cache: dict[str, PrefetchResult] = {}
        self._lock = asyncio.Lock()

    async def prefetch(self, task) -> None:
        """Run in background via asyncio.create_task()."""
        task_id = getattr(task, "id", "")
        description = getattr(task, "description", "") or ""
        loop = asyncio.get_running_loop()

        def _get_memory() -> str:
            if not self._memory_router or not description:
                return ""
            try:
                return self._memory_router.get_memory_context(description)
            except Exception:
                return ""

        def _get_tools():
            if not self._tool_selector:
                return []
            try:
                return self._tool_selector(
                    description,
                    role=getattr(task, "role", None),
                    score_store=self._score_store,
                )
            except Exception:
                return []

        memory_ctx = await loop.run_in_executor(None, _get_memory)
        tools = await loop.run_in_executor(None, _get_tools)
        async with self._lock:
            self._warmup_cache[task_id] = PrefetchResult(
                memory_context=memory_ctx,
                tools=tools,
                computed_at=datetime.now(timezone.utc),
            )

    def consume(self, task_id: str) -> PrefetchResult | None:
        """
        Called by Agent at start — returns pre-warmed context or None.
        Result older than max_age_seconds is treated as stale and not used.
        """
        result = self._warmup_cache.pop(task_id, None)
        if result is None:
            return None
        age_seconds = (
            datetime.now(timezone.utc) - result.computed_at
        ).total_seconds()
        if age_seconds > self._max_age_seconds:
            return None
        return result
