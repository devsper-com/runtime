"""
Semantic search across stored memory via embeddings and top_k retrieval.
"""

from devsper.memory.embeddings import embed_text
from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_types import MemoryRecord


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class MemoryIndex:
    """
    Vector search over memory. Uses store for persistence and optional
    embeddings on records for query_memory(text, top_k).
    """

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def query_memory(
        self,
        text: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
        include_archived: bool = False,
    ) -> list[MemoryRecord]:
        """
        Semantic search: embed query, score against stored records with embeddings,
        return top_k by similarity above min_similarity. Records without embeddings
        are skipped for ranking; if none have embeddings, return latest by timestamp.
        Use min_similarity > 0 (e.g. 0.45) to avoid injecting barely-related memory.
        By default excludes archived records (consolidation).
        """
        records = self.store.list_memory(limit=500, include_archived=include_archived)
        if not records:
            return []
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
    ) -> list[MemoryRecord]:
        """
        v1.8: Same as query_memory but over more records (all runs), optional run_id filter.
        Used by CrossRunSynthesizer. Excludes archived by default.
        """
        records = self.store.list_memory(
            limit=2000,
            include_archived=include_archived,
            run_id_filter=run_id_filter,
        )
        if not records:
            return []
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
