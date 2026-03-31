from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from devsper.tools.tool_runner import run_tool


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]
    task_type: str | None = None
    depends_on: tuple[str, ...] = ()
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ToolCallResult:
    id: str
    name: str
    output: str
    success: bool
    error: str | None
    started_at: datetime
    finished_at: datetime
    duration_ms: int


class ToolRunner:
    """Concurrency-limited tool invocation with batching and dependency handling."""

    def __init__(self, parallelism: int = 4, max_queue_size: int = 128) -> None:
        self._sem = asyncio.Semaphore(max(1, int(parallelism)))
        self._max_queue_size = max(1, int(max_queue_size))
        self._cancel_event = asyncio.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    async def run(self, name: str, args: dict, task_type: str | None = None) -> str:
        result = await self.run_call(
            ToolCall(
                id="single",
                name=name,
                args=args,
                task_type=task_type,
            )
        )
        return result.output

    async def run_call(self, call: ToolCall) -> ToolCallResult:
        if self._cancel_event.is_set():
            now = datetime.now(timezone.utc)
            return ToolCallResult(
                id=call.id,
                name=call.name,
                output="",
                success=False,
                error="cancelled",
                started_at=now,
                finished_at=now,
                duration_ms=0,
            )

        start = datetime.now(timezone.utc)

        async def _invoke() -> str:
            return await asyncio.to_thread(run_tool, call.name, call.args, call.task_type)

        async with self._sem:
            try:
                output = await asyncio.wait_for(
                    _invoke(),
                    timeout=max(0.1, float(call.timeout_seconds)),
                )
                end = datetime.now(timezone.utc)
                return ToolCallResult(
                    id=call.id,
                    name=call.name,
                    output=output or "",
                    success=not str(output or "").startswith("Tool error:"),
                    error=None,
                    started_at=start,
                    finished_at=end,
                    duration_ms=max(0, int((end - start).total_seconds() * 1000)),
                )
            except asyncio.TimeoutError:
                end = datetime.now(timezone.utc)
                return ToolCallResult(
                    id=call.id,
                    name=call.name,
                    output="",
                    success=False,
                    error=f"timeout after {call.timeout_seconds:.1f}s",
                    started_at=start,
                    finished_at=end,
                    duration_ms=max(0, int((end - start).total_seconds() * 1000)),
                )
            except asyncio.CancelledError:
                end = datetime.now(timezone.utc)
                return ToolCallResult(
                    id=call.id,
                    name=call.name,
                    output="",
                    success=False,
                    error="cancelled",
                    started_at=start,
                    finished_at=end,
                    duration_ms=max(0, int((end - start).total_seconds() * 1000)),
                )
            except Exception as exc:
                end = datetime.now(timezone.utc)
                return ToolCallResult(
                    id=call.id,
                    name=call.name,
                    output="",
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    started_at=start,
                    finished_at=end,
                    duration_ms=max(0, int((end - start).total_seconds() * 1000)),
                )

    async def run_many(self, calls: list[ToolCall]) -> list[ToolCallResult]:
        if not calls:
            return []
        if len(calls) > self._max_queue_size:
            raise ValueError(
                f"too many tool calls in one batch: {len(calls)} > {self._max_queue_size}"
            )

        by_id = {c.id: c for c in calls}
        completed: dict[str, ToolCallResult] = {}
        remaining = set(by_id.keys())

        while remaining and not self._cancel_event.is_set():
            ready = [
                by_id[cid]
                for cid in sorted(remaining)
                if all(dep in completed and completed[dep].success for dep in by_id[cid].depends_on)
            ]
            if not ready:
                # dependency cycle or failed prerequisite
                for cid in sorted(remaining):
                    call = by_id[cid]
                    now = datetime.now(timezone.utc)
                    completed[cid] = ToolCallResult(
                        id=call.id,
                        name=call.name,
                        output="",
                        success=False,
                        error="blocked by dependency failure or cycle",
                        started_at=now,
                        finished_at=now,
                        duration_ms=0,
                    )
                break

            results = await asyncio.gather(*(self.run_call(call) for call in ready))
            for result in results:
                completed[result.id] = result
                remaining.discard(result.id)

        return [completed[c.id] for c in calls if c.id in completed]

