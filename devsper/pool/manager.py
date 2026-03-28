from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .models import PoolTier, QueuedTask, WorkerRecord, WorkerStatus
from .store import PoolStore

log = logging.getLogger("devsper.pool")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


class PoolManager:
    """
    Resolves tasks to workers following the priority chain:
        dedicated -> org -> global -> wait queue (-> local only if profile=local)
    """

    def __init__(self, store: PoolStore, bus, config):
        self.store = store
        self.bus = bus
        self.config = config
        self._wait_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._inflight: dict[str, QueuedTask] = {}

    async def enqueue(self, task: QueuedTask) -> str:
        max_bytes = int(getattr(self.config, "max_payload_bytes", 1_048_576))
        if len(task.payload_enc) > max_bytes:
            raise PayloadTooLargeError("payload_too_large")
        if not await self.store.check_rate_limit(task.org_id, self.config.max_tasks_per_minute):
            raise RateLimitError("rate_limited")
        worker = await self._resolve_worker(task.org_id)
        if worker:
            await self._assign(task, worker)
            return worker.worker_id
        if self._wait_queue.qsize() >= getattr(self.config, "max_queue_depth", 100):
            raise QueueFullError("queue_full")
        await self._wait_queue.put((-task.priority, time.time(), task))
        return "queued"

    async def worker_free(self, worker_id: str):
        worker = await self.store.get_worker(worker_id)
        if not worker:
            return
        worker.status = WorkerStatus.IDLE
        if worker.current_task:
            self._inflight.pop(worker.current_task, None)
        worker.current_task = None
        worker.last_heartbeat = time.time()
        await self.store.save_worker(worker)
        await self._drain_queue_for(worker)

    async def register_worker(self, worker: WorkerRecord):
        await self.store.save_worker(worker)

    async def deregister_worker(self, worker_id: str):
        await self.store.delete_worker(worker_id)

    async def _resolve_worker(self, org_id: str) -> Optional[WorkerRecord]:
        w = await self._find_idle(PoolTier.DEDICATED, org_id)
        if w:
            return w
        w = await self._find_idle(PoolTier.ORG, org_id)
        if w:
            return w
        w = await self._find_idle(PoolTier.GLOBAL, None)
        if w:
            return w
        if getattr(self.config, "profile", "prod") == "local":
            w = await self._find_idle(PoolTier.LOCAL, None)
        return w

    async def _find_idle(self, tier: PoolTier, org_id: Optional[str]) -> Optional[WorkerRecord]:
        workers = await self.store.list_workers(tier=tier, org_id=org_id, status=WorkerStatus.IDLE)
        if not workers:
            return None
        return min(workers, key=lambda w: w.last_heartbeat)

    async def _assign(self, task: QueuedTask, worker: WorkerRecord):
        worker.status = WorkerStatus.BUSY
        worker.current_task = task.task_id
        worker.last_heartbeat = time.time()
        await self.store.save_worker(worker)
        self._inflight[task.task_id] = task
        # Publish encrypted payload; pool never decrypts.
        self.bus.publish(
            f"devsper:worker:{worker.worker_id}",
            {
                "event": "task.assigned",
                "task_id": task.task_id,
                "org_id": task.org_id,
                "payload_enc": task.payload_enc.hex(),
                "worker_id": worker.worker_id,
                "timestamp": _now(),
            },
        )

    async def evict_dead_workers(self):
        """
        Mark dead workers OFFLINE and requeue their current task (encrypted) for reassignment.
        """
        timeout_secs = int(getattr(self.config, "worker_timeout_secs", 90))
        for w in await self.store.list_all_workers():
            if w.status == WorkerStatus.OFFLINE:
                continue
            alive = await self.store.is_alive(w.worker_id)
            if alive:
                continue
            current = w.current_task
            w.status = WorkerStatus.OFFLINE
            w.current_task = None
            w.last_heartbeat = time.time()
            await self.store.save_worker(w)
            if current and current in self._inflight:
                t = self._inflight.pop(current)
                t.attempts += 1
                await self.enqueue(t)

    async def _drain_queue_for(self, worker: WorkerRecord):
        candidates = []
        while not self._wait_queue.empty():
            candidates.append(await self._wait_queue.get())

        org_tasks = [t for t in candidates if worker.org_id and t[2].org_id == worker.org_id]
        other = [t for t in candidates if not (worker.org_id and t[2].org_id == worker.org_id)]

        assigned = False
        for batch in (org_tasks, other):
            for item in batch:
                if not assigned:
                    await self._assign(item[2], worker)
                    assigned = True
                else:
                    await self._wait_queue.put(item)
            if assigned:
                for item in (other if batch is org_tasks else []):
                    await self._wait_queue.put(item)
                break
        if not assigned:
            for item in candidates:
                await self._wait_queue.put(item)


class RateLimitError(Exception):
    pass


class PayloadTooLargeError(Exception):
    pass


class QueueFullError(Exception):
    pass

