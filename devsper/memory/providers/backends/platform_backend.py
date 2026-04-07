"""
PlatformBackend: wraps PlatformMemoryStore for users with backend = "platform".

Preserves existing behavior for the platform API memory path.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from devsper.memory.providers.base import MemoryBackend, MemoryQuery

if TYPE_CHECKING:
    from devsper.memory.platform_memory import PlatformMemoryStore
    from devsper.memory.memory_types import MemoryRecord, MemoryType


class PlatformBackend(MemoryBackend):
    """Remote platform API memory store. Preserves backend = 'platform' behavior."""

    def __init__(self, base_url: str = "", org_slug: str = "") -> None:
        from devsper.memory.platform_memory import PlatformMemoryStore

        self._store = PlatformMemoryStore(base_url=base_url, org_slug=org_slug)

    @property
    def name(self) -> str:
        return "platform"

    def get_sync_store(self) -> "PlatformMemoryStore":
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
            memory_type, limit, offset, tag_contains,
            include_archived, run_id_filter, namespace,
        )

    async def list_all_ids(
        self,
        memory_type: "MemoryType | None" = None,
        namespace: str | None = None,
    ) -> list[str]:
        return await asyncio.to_thread(self._store.list_all_ids, memory_type, namespace)

    async def query_similar(self, query: MemoryQuery) -> "list[MemoryRecord]":
        return []

    async def health(self) -> bool:
        try:
            await asyncio.to_thread(self._store.list_memory, None, 1)
            return True
        except Exception:
            return False
