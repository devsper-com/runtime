"""
Abstract MemoryBackend interface — analogous to LLMBackend in providers/router/base.py.

All memory providers implement this async interface.
Sync backends (SQLite, Redis) wrap their stores via asyncio.to_thread internally
and expose get_sync_store() for legacy callers that can't be async.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devsper.memory.memory_types import MemoryRecord, MemoryType


@dataclass
class MemoryQuery:
    """Unified query structure for semantic search — analogous to LLMRequest."""

    text: str
    top_k: int = 5
    min_similarity: float = 0.0
    namespace: str | None = None
    include_archived: bool = False


class MemoryBackend(ABC):
    """
    Abstract async interface for all memory backends.
    Mirrors LLMBackend from providers/router/base.py.

    Backends that wrap synchronous stores (SQLite, Redis) should expose
    get_sync_store() so legacy sync callers in MemoryRouter/tools can access
    the underlying store without an async bridge.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: 'sqlite', 'redis', 'snowflake', 'vektori'."""
        ...

    @property
    def supports_native_vector_search(self) -> bool:
        """
        Return True if this backend performs vector/semantic search natively
        (e.g. Snowflake VECTOR_COSINE_SIMILARITY, pgvector <=>).
        When False, MemoryIndex falls back to in-process cosine ranking.
        """
        return False

    @abstractmethod
    async def store(
        self,
        record: "MemoryRecord",
        namespace: str | None = None,
    ) -> str:
        """Persist a memory record. Return the memory_id."""
        ...

    @abstractmethod
    async def retrieve(
        self,
        memory_id: str,
        namespace: str | None = None,
    ) -> "MemoryRecord | None":
        """Fetch a single record by id. Return None if not found."""
        ...

    @abstractmethod
    async def delete(
        self,
        memory_id: str,
        namespace: str | None = None,
    ) -> bool:
        """Delete a record. Return True if a row was removed."""
        ...

    @abstractmethod
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
        """List records with optional filters. Mirrors MemoryStore.list_memory()."""
        ...

    @abstractmethod
    async def list_all_ids(
        self,
        memory_type: "MemoryType | None" = None,
        namespace: str | None = None,
    ) -> list[str]:
        """Return all memory IDs. Used by MemoryIndex for index sync."""
        ...

    @abstractmethod
    async def query_similar(
        self,
        query: MemoryQuery,
    ) -> "list[MemoryRecord]":
        """
        Semantic/vector similarity search.
        Backends without native support should return [] — MemoryIndex will
        then handle in-process ranking via embed_text + cosine similarity.
        Backends with supports_native_vector_search=True return ranked results.
        """
        ...

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the backend is reachable and operational."""
        ...

    async def close(self) -> None:
        """Clean up connections/resources. Override if needed."""
        return None
