"""
In-memory embedding index for semantic cache lookup. Uses same embedding provider as memory.
"""

import io
from typing import Any

import numpy as np

from devsper.memory.embeddings import embed_text


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embedding_to_bytes(vec: list[float]) -> bytes:
    arr = np.array(vec, dtype=np.float64)
    buf = io.BytesIO()
    np.save(buf, arr, allow_pickle=False)
    return buf.getvalue()


def _bytes_to_embedding(data: bytes) -> list[float]:
    buf = io.BytesIO(data)
    arr = np.load(buf, allow_pickle=False)
    return arr.tolist()


class CacheEmbeddingIndex:
    """
    Same embedding provider as memory (embed_text). Loads entries from store,
    keeps vectors in memory for nearest-neighbor search.
    """

    def __init__(self, store: Any = None) -> None:
        self.store = store
        self._vectors: list[list[float]] = []
        self._meta: list[tuple[str, str, str, float, str]] = []  # key, result, task_type, created_at, original_description

    def rebuild(self) -> None:
        """Load all semantic entries from store and index by embedding."""
        self._vectors = []
        self._meta = []
        if not self.store:
            return
        for emb_blob, result, task_type, created_at, key, original_desc in self.store.list_semantic_entries():
            vec = _bytes_to_embedding(emb_blob)
            self._vectors.append(vec)
            self._meta.append((key, result, task_type, created_at, original_desc))

    def add(self, embedding: list[float], key: str, result: str, task_type: str, created_at: float, original_description: str) -> None:
        self._vectors.append(embedding)
        self._meta.append((key, result, task_type, created_at, original_description))

    def search(
        self,
        query_embedding: list[float],
        threshold: float,
        max_age_seconds: float,
    ) -> tuple[float, str, str, str, str, str] | None:
        """
        Nearest neighbor search. Returns (similarity, result, original_description, cached_at, task_type, key)
        for best match >= threshold and not expired, or None.
        """
        import time
        now = time.time()
        best_sim = -1.0
        best = None
        for i, vec in enumerate(self._vectors):
            sim = _cosine_sim(query_embedding, vec)
            if sim < threshold:
                continue
            key, result, task_type, created_at, original_desc = self._meta[i]
            if max_age_seconds > 0 and (now - created_at) > max_age_seconds:
                continue
            if sim > best_sim:
                best_sim = sim
                best = (result, original_desc, created_at, task_type, key)
        if best is None:
            return None
        result, original_desc, created_at, task_type, key = best
        return (best_sim, result, original_desc, str(created_at), task_type, key)


def embedding_to_bytes(vec: list[float]) -> bytes:
    return _embedding_to_bytes(vec)


def bytes_to_embedding(data: bytes) -> list[float]:
    return _bytes_to_embedding(data)
