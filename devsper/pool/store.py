from __future__ import annotations

import json
import time
from typing import Optional, Protocol

from .models import NodeRecord, PoolTier, WorkerRecord, WorkerStatus


class PoolStore(Protocol):
    async def save_worker(self, w: WorkerRecord): ...
    async def get_worker(self, worker_id: str) -> Optional[WorkerRecord]: ...
    async def delete_worker(self, worker_id: str): ...
    async def list_workers(
        self, tier: PoolTier, org_id: Optional[str], status: Optional[WorkerStatus]
    ) -> list[WorkerRecord]: ...
    async def list_all_workers(self) -> list[WorkerRecord]: ...

    async def save_node(self, n: NodeRecord): ...
    async def get_node(self, node_id: str) -> Optional[NodeRecord]: ...

    async def heartbeat(self, worker_id: str, ttl_secs: int = 90): ...
    async def is_alive(self, worker_id: str) -> bool: ...

    async def check_rate_limit(self, org_id: str, limit: int) -> bool: ...


class RedisPoolStore:
    """
    Redis-backed state store.

    Key schema:
      pool:worker:{worker_id}         -> WorkerRecord JSON
      pool:node:{node_id}             -> NodeRecord JSON
      pool:org:{org_id}:workers       -> SET worker_ids
      pool:tier:{tier}:workers        -> SET worker_ids
      pool:worker:{worker_id}:hb      -> heartbeat (TTL)
      pool:ratelimit:{org_id}         -> counter (TTL 60)
    """

    def __init__(self, redis_url: str):
        import redis.asyncio as aioredis

        self._r = aioredis.from_url(redis_url, decode_responses=True)

    async def save_worker(self, w: WorkerRecord):
        key = f"pool:worker:{w.worker_id}"
        await self._r.set(key, json.dumps(_worker_to_dict(w)))
        await self._r.sadd(f"pool:tier:{w.tier.value}:workers", w.worker_id)
        if w.org_id:
            await self._r.sadd(f"pool:org:{w.org_id}:workers", w.worker_id)

    async def get_worker(self, worker_id: str) -> Optional[WorkerRecord]:
        raw = await self._r.get(f"pool:worker:{worker_id}")
        return _worker_from_dict(json.loads(raw)) if raw else None

    async def delete_worker(self, worker_id: str):
        w = await self.get_worker(worker_id)
        if not w:
            return
        await self._r.delete(f"pool:worker:{worker_id}")
        await self._r.srem(f"pool:tier:{w.tier.value}:workers", worker_id)
        if w.org_id:
            await self._r.srem(f"pool:org:{w.org_id}:workers", worker_id)

    async def list_workers(
        self, tier: PoolTier, org_id: Optional[str], status: Optional[WorkerStatus]
    ) -> list[WorkerRecord]:
        if org_id:
            ids = await self._r.sinter(
                f"pool:tier:{tier.value}:workers",
                f"pool:org:{org_id}:workers",
            )
        else:
            ids = await self._r.smembers(f"pool:tier:{tier.value}:workers")
        workers: list[WorkerRecord] = []
        for wid in ids:
            w = await self.get_worker(wid)
            if not w:
                continue
            if status is None or w.status == status:
                workers.append(w)
        return workers

    async def list_all_workers(self) -> list[WorkerRecord]:
        # Best-effort: union of known tiers.
        ids = set()
        for tier in (PoolTier.DEDICATED, PoolTier.ORG, PoolTier.GLOBAL, PoolTier.LOCAL):
            for wid in await self._r.smembers(f"pool:tier:{tier.value}:workers"):
                ids.add(wid)
        out: list[WorkerRecord] = []
        for wid in ids:
            w = await self.get_worker(wid)
            if w:
                out.append(w)
        return out

    async def save_node(self, n: NodeRecord):
        await self._r.set(f"pool:node:{n.node_id}", json.dumps(_node_to_dict(n)))

    async def get_node(self, node_id: str) -> Optional[NodeRecord]:
        raw = await self._r.get(f"pool:node:{node_id}")
        return _node_from_dict(json.loads(raw)) if raw else None

    async def heartbeat(self, worker_id: str, ttl_secs: int = 90):
        await self._r.setex(f"pool:worker:{worker_id}:hb", ttl_secs, "1")

    async def is_alive(self, worker_id: str) -> bool:
        return bool(await self._r.exists(f"pool:worker:{worker_id}:hb"))

    async def check_rate_limit(self, org_id: str, limit: int) -> bool:
        key = f"pool:ratelimit:{org_id}"
        count = await self._r.incr(key)
        if count == 1:
            await self._r.expire(key, 60)
        return int(count) <= limit


class InMemoryPoolStore:
    def __init__(self):
        self.workers: dict[str, WorkerRecord] = {}
        self.nodes: dict[str, NodeRecord] = {}
        self.hb_expiry: dict[str, float] = {}
        self.ratelimit: dict[str, tuple[int, float]] = {}

    async def save_worker(self, w: WorkerRecord):
        self.workers[w.worker_id] = w

    async def get_worker(self, worker_id: str) -> Optional[WorkerRecord]:
        return self.workers.get(worker_id)

    async def delete_worker(self, worker_id: str):
        self.workers.pop(worker_id, None)
        self.hb_expiry.pop(worker_id, None)

    async def list_workers(
        self, tier: PoolTier, org_id: Optional[str], status: Optional[WorkerStatus]
    ) -> list[WorkerRecord]:
        out: list[WorkerRecord] = []
        for w in self.workers.values():
            if w.tier != tier:
                continue
            if org_id is None:
                if w.org_id is not None and tier == PoolTier.GLOBAL:
                    continue
            else:
                if w.org_id != org_id:
                    continue
            if status is None or w.status == status:
                out.append(w)
        return out

    async def list_all_workers(self) -> list[WorkerRecord]:
        return list(self.workers.values())

    async def save_node(self, n: NodeRecord):
        self.nodes[n.node_id] = n

    async def get_node(self, node_id: str) -> Optional[NodeRecord]:
        return self.nodes.get(node_id)

    async def heartbeat(self, worker_id: str, ttl_secs: int = 90):
        self.hb_expiry[worker_id] = time.time() + ttl_secs

    async def is_alive(self, worker_id: str) -> bool:
        exp = self.hb_expiry.get(worker_id)
        return bool(exp and exp > time.time())

    async def check_rate_limit(self, org_id: str, limit: int) -> bool:
        now = time.time()
        count, window_end = self.ratelimit.get(org_id, (0, 0.0))
        if window_end <= now:
            count, window_end = 0, now + 60.0
        count += 1
        self.ratelimit[org_id] = (count, window_end)
        return count <= limit


def _worker_to_dict(w: WorkerRecord) -> dict:
    d = w.__dict__.copy()
    d["tier"] = w.tier.value
    d["status"] = w.status.value
    return d


def _worker_from_dict(d: dict) -> WorkerRecord:
    d = dict(d)
    d["tier"] = PoolTier(d["tier"])
    d["status"] = WorkerStatus(d["status"])
    return WorkerRecord(**d)


def _node_to_dict(n: NodeRecord) -> dict:
    d = n.__dict__.copy()
    d["tier"] = n.tier.value
    return d


def _node_from_dict(d: dict) -> NodeRecord:
    d = dict(d)
    d["tier"] = PoolTier(d["tier"])
    return NodeRecord(**d)

