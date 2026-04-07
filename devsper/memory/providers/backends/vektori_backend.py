"""
VektoriBackend: wraps _PgVectorMemory from server/memory_utils.py.

This is the default production backend. Requires:
  - DATABASE_URL (Postgres with pgvector + migration 018 applied)
  - OPENAI_API_KEY (or VEKTORI_USE_MOCK_EMBEDDINGS=1 for dev/CI)

Note: Vektori's schema (vektori_facts) does not have a primary-key lookup path,
so retrieve() and delete() by memory_id are not supported. Use query_similar()
for semantic search.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from devsper.memory.providers.base import MemoryBackend, MemoryQuery

if TYPE_CHECKING:
    from devsper.memory.memory_types import MemoryRecord, MemoryType

log = logging.getLogger(__name__)


def _hit_to_record(hit: object) -> "MemoryRecord":
    """Convert a _MemHit from _PgVectorMemory.search() to a MemoryRecord."""
    from devsper.memory.memory_types import MemoryRecord, MemoryType

    text = str(getattr(hit, "text", "") or "")
    score = getattr(hit, "score", None)
    return MemoryRecord(
        id=str(uuid.uuid4()),
        memory_type=MemoryType.EPISODIC,
        content=text,
        tags=[],
        timestamp=datetime.now(timezone.utc),
        source_task="vektori",
        embedding=None,
        run_id="",
        archived=False,
    )


class VektoriBackend(MemoryBackend):
    """
    pgvector-backed memory via the embedded Vektori store (vektori_facts table).
    This is the default production backend.
    """

    @property
    def name(self) -> str:
        return "vektori"

    @property
    def supports_native_vector_search(self) -> bool:
        return True

    async def store(self, record: "MemoryRecord", namespace: str | None = None) -> str:
        from devsper.server.memory_utils import get_vektori

        v = await get_vektori()
        msgs = [{"role": "assistant", "content": record.content}]
        user_id = namespace or "devsper:global"
        session_id = f"run:{record.run_id}" if record.run_id else f"manual:{record.id}"
        await v.add(messages=msgs, user_id=user_id, session_id=session_id)
        return record.id

    async def retrieve(self, memory_id: str, namespace: str | None = None) -> "MemoryRecord | None":
        # Vektori's vektori_facts table does not expose a primary-key lookup.
        # Use query_similar() for semantic retrieval.
        raise NotImplementedError(
            "VektoriBackend does not support retrieval by memory_id. "
            "Use query_similar() for semantic search."
        )

    async def delete(self, memory_id: str, namespace: str | None = None) -> bool:
        raise NotImplementedError(
            "VektoriBackend does not support deletion by memory_id."
        )

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
        # Best-effort: do a broad search with a generic query
        try:
            query = MemoryQuery(text="*", top_k=limit, namespace=namespace)
            return await self.query_similar(query)
        except Exception:
            return []

    async def list_all_ids(
        self,
        memory_type: "MemoryType | None" = None,
        namespace: str | None = None,
    ) -> list[str]:
        # Not efficiently supported by vektori_facts schema
        records = await self.list_memory(namespace=namespace)
        return [r.id for r in records]

    async def query_similar(self, query: MemoryQuery) -> "list[MemoryRecord]":
        from devsper.server.memory_utils import get_vektori

        try:
            v = await get_vektori()
            hits = await v.search(
                query=query.text,
                user_id=query.namespace or "devsper:global",
            )
            return [_hit_to_record(h) for h in hits[: query.top_k]]
        except Exception as e:
            log.warning("vektori_query_similar_failed error=%s", e)
            return []

    async def health(self) -> bool:
        try:
            from devsper.server.memory_utils import get_vektori

            await get_vektori()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        try:
            from devsper.server.memory_utils import close_vektori

            await close_vektori()
        except Exception:
            pass
