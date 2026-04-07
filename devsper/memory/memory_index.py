"""
Semantic search across stored memory via embeddings and top_k retrieval.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from devsper.memory.embeddings import embed_text
from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_types import MemoryRecord
from devsper.memory.supermemory_rust_ranker import rank_memories

if TYPE_CHECKING:
    from devsper.memory.providers.base import MemoryBackend


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _run_async_in_thread(coro):
    """Run a coroutine synchronously, safely bridging from sync context."""
    import asyncio
    import concurrent.futures

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class MemoryIndex:
    """
    Vector search over memory. Uses store for persistence and optional
    embeddings on records for query_memory(text, top_k).

    When a MemoryBackend with supports_native_vector_search=True is provided,
    query_memory() and query_across_runs() delegate to the backend's native
    vector search (e.g. Snowflake VECTOR_COSINE_SIMILARITY, pgvector <=>),
    bypassing in-process cosine ranking.
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        ranking_backend: str = "local",
        backend: "MemoryBackend | None" = None,
    ) -> None:
        self._backend = backend
        if store is not None:
            self.store = store
        elif backend is not None and hasattr(backend, "get_sync_store"):
            self.store = backend.get_sync_store()
        else:
            self.store = store or MemoryStore()
        self.ranking_backend = ranking_backend

    def query_memory(
        self,
        text: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
        include_archived: bool = False,
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        """
        Semantic search via ranking strategy:
        - native (vektori/snowflake): delegates to backend.query_similar() directly.
        - local (default): embed query, cosine-rank records that have embeddings.
        - supermemory: hybrid local ranking (lexical token overlap + optional embedding
          cosine similarity) using `rank_memories()`; records without embeddings can
          still be ranked via lexical overlap.

        Candidates with final_score < min_similarity are dropped (when min_similarity > 0).
        Use min_similarity > 0 (e.g. 0.45) to avoid injecting barely-related memory.
        By default excludes archived records (consolidation).
        """
        # Fast path: delegate to native vector search when supported
        if self._backend is not None and self._backend.supports_native_vector_search:
            try:
                from devsper.memory.providers.base import MemoryQuery

                query = MemoryQuery(
                    text=text,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    namespace=namespace,
                    include_archived=include_archived,
                )
                return _run_async_in_thread(self._backend.query_similar(query))
            except Exception:
                pass  # fall through to in-process ranking

        records = self.store.list_memory(
            limit=500, include_archived=include_archived, namespace=namespace
        )
        if not records:
            return []

        if self.ranking_backend == "supermemory":
            # Prepare candidates for local hybrid ranking.
            candidates = [
                {
                    "id": r.id,
                    "content": r.content,
                    "tags": r.tags,
                    "embedding": r.embedding,
                    "timestamp": r.timestamp.isoformat(),
                    "memory_type": r.memory_type.value,
                    "source_task": r.source_task,
                }
                for r in records
            ]
            with_emb = any(c.get("embedding") is not None for c in candidates)
            query_emb = embed_text(text) if with_emb else None
            ranked = rank_memories(
                query_text=text,
                query_embedding=query_emb,
                candidates=candidates,
                top_k=top_k,
                min_similarity=min_similarity,
            )
            id_map = {r.id: r for r in records}
            out: list[MemoryRecord] = []
            for x in ranked:
                rid = str(x.get("id", ""))
                r = id_map.get(rid)
                if r is not None:
                    out.append(r)
            return out

        query_emb = embed_text(text)
        with_emb = [r for r in records if r.embedding is not None]
        if not with_emb:
            return records[:top_k]
        scored = [
            (_cosine_sim(query_emb, r.embedding), r)
            for r in with_emb
        ]
        scored.sort(key=lambda x: -x[0])
        if min_similarity > 0:
            scored = [(s, r) for s, r in scored if s >= min_similarity]
        return [r for _, r in scored[:top_k]]

    def query_across_runs(
        self,
        text: str,
        top_k: int = 20,
        min_similarity: float = 0.0,
        run_id_filter: str | None = None,
        include_archived: bool = False,
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        """
        v1.8: Same as query_memory but over more records (all runs), optional run_id filter.
        Used by CrossRunSynthesizer. Excludes archived by default.
        """
        # Fast path: delegate to native vector search when supported
        if self._backend is not None and self._backend.supports_native_vector_search:
            try:
                from devsper.memory.providers.base import MemoryQuery

                query = MemoryQuery(
                    text=text,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    namespace=namespace,
                    include_archived=include_archived,
                )
                return _run_async_in_thread(self._backend.query_similar(query))
            except Exception:
                pass  # fall through to in-process ranking

        records = self.store.list_memory(
            limit=2000,
            include_archived=include_archived,
            run_id_filter=run_id_filter,
            namespace=namespace,
        )
        if not records:
            return []

        if self.ranking_backend == "supermemory":
            candidates = [
                {
                    "id": r.id,
                    "content": r.content,
                    "tags": r.tags,
                    "embedding": r.embedding,
                    "timestamp": r.timestamp.isoformat(),
                    "memory_type": r.memory_type.value,
                    "source_task": r.source_task,
                }
                for r in records
            ]
            with_emb = any(c.get("embedding") is not None for c in candidates)
            query_emb = embed_text(text) if with_emb else None
            ranked = rank_memories(
                query_text=text,
                query_embedding=query_emb,
                candidates=candidates,
                top_k=top_k,
                min_similarity=min_similarity,
            )
            id_map = {r.id: r for r in records}
            out: list[MemoryRecord] = []
            for x in ranked:
                rid = str(x.get("id", ""))
                r = id_map.get(rid)
                if r is not None:
                    out.append(r)
            return out

        query_emb = embed_text(text)
        with_emb = [r for r in records if r.embedding is not None]
        if not with_emb:
            return records[:top_k]
        scored = [
            (_cosine_sim(query_emb, r.embedding), r)
            for r in with_emb
        ]
        scored.sort(key=lambda x: -x[0])
        if min_similarity > 0:
            scored = [(s, r) for s, r in scored if s >= min_similarity]
        return [r for _, r in scored[:top_k]]

    def ensure_embedding(self, record: MemoryRecord) -> MemoryRecord:
        """Compute and attach embedding if missing; return record (unchanged if already set)."""
        if record.embedding is not None:
            return record
        record.embedding = embed_text(record.content)
        return record
