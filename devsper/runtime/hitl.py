from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class HITLRequest:
    request_id: str
    task_id: str
    prompt: str
    timeout_seconds: int = 120


@dataclass(frozen=True)
class HITLResponse:
    request_id: str
    approved: bool
    payload: dict[str, Any]


class HITLManager:
    """Pause/resume manager for human-in-the-loop checkpoints."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[HITLResponse]] = {}
        self._paused_tasks: set[str] = set()
        self._lock = asyncio.Lock()

    async def pause_task(self, task_id: str) -> None:
        async with self._lock:
            self._paused_tasks.add(task_id)

    async def resume_task(self, task_id: str) -> None:
        async with self._lock:
            self._paused_tasks.discard(task_id)

    async def request_human_input(self, req: HITLRequest) -> HITLResponse:
        await self.pause_task(req.task_id)
        fut: asyncio.Future[HITLResponse] = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._pending[req.request_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=float(req.timeout_seconds))
        except asyncio.TimeoutError:
            return HITLResponse(request_id=req.request_id, approved=False, payload={"reason": "timeout"})
        finally:
            async with self._lock:
                self._pending.pop(req.request_id, None)
            await self.resume_task(req.task_id)

    async def submit_response(self, response: HITLResponse) -> None:
        async with self._lock:
            fut = self._pending.get(response.request_id)
        if fut is not None and not fut.done():
            fut.set_result(response)

    def is_paused(self, task_id: str) -> bool:
        return task_id in self._paused_tasks

    def event_payload(self, req: HITLRequest) -> dict[str, Any]:
        return {
            "request_id": req.request_id,
            "task_id": req.task_id,
            "prompt": req.prompt,
            "timeout_seconds": req.timeout_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

