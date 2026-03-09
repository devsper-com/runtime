"""Shared state backend for scheduler snapshots (Redis or filesystem)."""

import json
import os
from abc import ABC, abstractmethod


class StateBackend(ABC):
    """Abstract backend for saving/loading scheduler snapshots."""

    @abstractmethod
    async def save_snapshot(self, run_id: str, snapshot: dict) -> None:
        ...

    @abstractmethod
    async def load_snapshot(self, run_id: str) -> dict | None:
        ...

    @abstractmethod
    async def delete_snapshot(self, run_id: str) -> None:
        ...

    @abstractmethod
    async def list_snapshots(self) -> list[str]:
        ...


class RedisStateBackend(StateBackend):
    """Store snapshots in Redis. Key: hivemind:snapshot:{run_id}, set index: hivemind:snapshots."""

    def __init__(self, redis_client: object) -> None:
        self._redis = redis_client
        self._key_prefix = "hivemind:snapshot:"
        self._index_key = "hivemind:snapshots"

    async def save_snapshot(self, run_id: str, snapshot: dict) -> None:
        key = f"{self._key_prefix}{run_id}"
        await self._redis.set(key, json.dumps(snapshot))
        await self._redis.sadd(self._index_key, run_id)

    async def load_snapshot(self, run_id: str) -> dict | None:
        key = f"{self._key_prefix}{run_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def delete_snapshot(self, run_id: str) -> None:
        key = f"{self._key_prefix}{run_id}"
        await self._redis.delete(key)
        await self._redis.srem(self._index_key, run_id)

    async def list_snapshots(self) -> list[str]:
        members = await self._redis.smembers(self._index_key)
        return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members]


class FilesystemStateBackend(StateBackend):
    """Single-node: write snapshots to events_dir as {run_id}.snapshot.json. Atomic write."""

    def __init__(self, events_dir: str) -> None:
        self._events_dir = events_dir

    def _path(self, run_id: str) -> str:
        return os.path.join(self._events_dir, f"{run_id}.snapshot.json")

    async def save_snapshot(self, run_id: str, snapshot: dict) -> None:
        path = self._path(run_id)
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=0)
        os.replace(tmp, path)

    async def load_snapshot(self, run_id: str) -> dict | None:
        path = self._path(run_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def delete_snapshot(self, run_id: str) -> None:
        path = self._path(run_id)
        if os.path.isfile(path):
            os.remove(path)

    async def list_snapshots(self) -> list[str]:
        if not os.path.isdir(self._events_dir):
            return []
        out: list[str] = []
        for name in os.listdir(self._events_dir):
            if name.endswith(".snapshot.json"):
                out.append(name.removesuffix(".snapshot.json"))
        return out


def get_state_backend(config: object, redis_client: object | None = None) -> StateBackend:
    """Return StateBackend from config. Redis if bus.backend == redis else filesystem."""
    backend = getattr(getattr(config, "bus", None), "backend", "memory")
    if backend == "redis" and redis_client is not None:
        return RedisStateBackend(redis_client)
    events_dir = getattr(config, "events_dir", ".hivemind/events")
    return FilesystemStateBackend(events_dir)
