from __future__ import annotations

import asyncio
from dataclasses import dataclass

from devsper.cluster.router import TaskRouter
from devsper.types.task import Task


@dataclass
class WorkerState:
    worker_id: str
    healthy: bool = True
    active_tasks: int = 0
    max_workers: int = 1


class DistributedController:
    """Controller-side worker orchestration and task assignment."""

    def __init__(self, router: TaskRouter | None = None) -> None:
        self._router = router or TaskRouter()
        self._workers: dict[str, WorkerState] = {}
        self._task_assignments: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register_worker(self, worker_id: str, max_workers: int = 1) -> None:
        async with self._lock:
            self._workers[worker_id] = WorkerState(
                worker_id=worker_id,
                healthy=True,
                active_tasks=0,
                max_workers=max(1, int(max_workers)),
            )

    async def mark_worker_unhealthy(self, worker_id: str) -> None:
        async with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id].healthy = False

    async def health_check(self) -> dict[str, bool]:
        async with self._lock:
            return {wid: ws.healthy for wid, ws in self._workers.items()}

    async def assign_task(self, task: Task) -> str | None:
        async with self._lock:
            candidates = [
                ws
                for ws in self._workers.values()
                if ws.healthy and ws.active_tasks < ws.max_workers
            ]
            if not candidates:
                return None
            # Lightweight balancing by active load.
            candidates.sort(key=lambda ws: (ws.active_tasks / max(1, ws.max_workers), ws.worker_id))
            chosen = candidates[0]
            chosen.active_tasks += 1
            self._task_assignments[task.id] = chosen.worker_id
            return chosen.worker_id

    async def complete_task(self, task_id: str) -> None:
        async with self._lock:
            wid = self._task_assignments.pop(task_id, None)
            if wid and wid in self._workers:
                self._workers[wid].active_tasks = max(0, self._workers[wid].active_tasks - 1)

    async def reassign_on_failure(self, task: Task, failed_worker_id: str) -> str | None:
        await self.mark_worker_unhealthy(failed_worker_id)
        return await self.assign_task(task)

