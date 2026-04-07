"""
RedisBackend: wraps the existing synchronous RedisMemoryStore via asyncio.to_thread.

Exposes get_sync_store() for legacy callers that can't be async.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from devsper.memory.providers.base import MemoryBackend, MemoryQuery

if TYPE_CHECKING:
    from devsper.memory.redis_memory import RedisMemoryStore
    from devsper.memory.memory_types import MemoryRecord, MemoryType


class RedisBackend(MemoryBackend):
    """Redis-backed distributed memory store."""

    def __init__(
        self,
        redis_url: str,
        run_id: str,
        default_namespace: str | None = None,
    ) -> None:
        from devsper.memory.redis_memory import RedisMemoryStore

        self._store = RedisMemoryStore(
            redis_url=redis_url,
            run_id=run_id,
            default_namespace=default_namespace,
        )

    @property
    def name(self) -> str:
        return "redis"

    def get_sync_store(self) -> "RedisMemoryStore":
        """Return the underlying sync RedisMemoryStore for legacy callers."""
        return self._store

    async def store(self, record: "MemoryRecord", namespace: str | None = None) -> str:
        return await asyncio.to_thread(self._store.store, record, namespace)

    async def retrieve(self, memory_id: str, namespace: str | None = None) -> "MemoryRecord | None":
        return await asyncio.to_thread(self._store.retrieve, memory_id, namespace)

    async def delete(self, memory_id: str, namespace: str | None = None) -> bool:
        return await asyncio.to_thread(self._store.delete, memory_id, namespace)

    async def list_memory(
        self,
        memory_type: "MemoryType | None" = None,
        limit: int = 100,
        offset: int = 0,
        tag_contains: str | None = None,
        include_archived: bool = False,
        run_id_filter: str | None = None,
        namespace: str | None = None,
    ) -> "list[MemoryRecord]":
        return await asyncio.to_thread(
            self._store.list_memory,
            memory_type,
            limit,
            offset,
            tag_contains,
            include_archived,
            run_id_filter,
            namespace,
        )

    async def list_all_ids(
        self,
        memory_type: "MemoryType | None" = None,
        namespace: str | None = None,
    ) -> list[str]:
        return await asyncio.to_thread(self._store.list_all_ids, memory_type, namespace)

    async def query_similar(self, query: MemoryQuery) -> "list[MemoryRecord]":
        # No native vector search — MemoryIndex handles in-process cosine ranking.
        return []

    async def health(self) -> bool:
        try:
            await asyncio.to_thread(self._store._redis.ping)
            return True
        except Exception:
            return False
