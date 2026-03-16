"""
Persistent task result cache. Before executing a task, hash(task) and check cache;
on hit return cached result. Store uses SQLite.

v1.6: SemanticTaskCache for embedding-based similarity lookup; CacheHit dataclass.
"""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from devsper.types.task import Task
from devsper.cache.hashing import task_hash


@dataclass
class CacheHit:
    """Result of a semantic cache lookup."""
    result: str
    similarity: float
    original_description: str
    cached_at: str
    task_type: str


class TaskCache:
    """SQLite-backed cache: get(task) -> result or None, set(task, result)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(".devsper") / "task_cache.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS task_cache (
                    key TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    created_at REAL
                )
                """)

    def get(self, task: Task) -> str | None:
        """Return cached result for task if present; else None."""
        key = task_hash(
            task.id,
            task.description or "",
            task.dependencies or [],
        )
        with self._conn() as c:
            row = c.execute(
                "SELECT result FROM task_cache WHERE key = ?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def set(self, task: Task, result: str) -> None:
        """Store result for task."""
        import time

        key = task_hash(
            task.id,
            task.description or "",
            task.dependencies or [],
        )
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO task_cache (key, result, created_at) VALUES (?, ?, ?)",
                (key, result, time.time()),
            )

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._conn() as c:
            c.execute("DELETE FROM task_cache")

    def stats(self) -> dict:
        """Return count of cached entries."""
        with self._conn() as c:
            n = c.execute("SELECT COUNT(*) FROM task_cache").fetchone()[0]
        return {"entries": n}


def _default_store():
    from devsper.cache.store import get_default_cache_store
    return get_default_cache_store(Path(".devsper") / "task_cache.db")


class SemanticTaskCache:
    """
    Semantic similarity cache: embed task description, search for nearest neighbor,
    return CacheHit if similarity >= threshold and not expired.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        store=None,
        max_age_hours: float = 168.0,
    ) -> None:
        self.threshold = similarity_threshold
        self.store = store or _default_store()
        self.max_age_seconds = max_age_hours * 3600.0
        from devsper.cache.embedding_index import CacheEmbeddingIndex
        self.index = CacheEmbeddingIndex(self.store)
        self.index.rebuild()
        self._last_query: str | None = None
        self._last_embedding: list[float] | None = None

    def lookup(self, task_description: str) -> CacheHit | None:
        """
        1. Embed task_description
        2. Search index for nearest neighbor
        3. If similarity >= threshold AND result not expired: return CacheHit
        4. Otherwise: return None
        """
        from devsper.memory.embeddings import embed_text
        desc = (task_description or "").strip()
        if not desc:
            return None
        if desc == self._last_query and self._last_embedding is not None:
            query_emb = self._last_embedding
        else:
            query_emb = embed_text(desc)
            self._last_query = desc
            self._last_embedding = query_emb
        hit = self.index.search(
            query_emb,
            threshold=self.threshold,
            max_age_seconds=self.max_age_seconds,
        )
        if hit is None:
            return None
        sim, result, original_description, cached_at, task_type, _key = hit
        return CacheHit(
            result=result,
            similarity=sim,
            original_description=original_description,
            cached_at=cached_at,
            task_type=task_type,
        )

    def store_result(self, task_description: str, result: str, task_type: str) -> None:
        """
        Embed task_description, store (embedding, result, task_type, timestamp),
        add to index.
        """
        from devsper.memory.embeddings import embed_text
        from devsper.cache.embedding_index import embedding_to_bytes
        if not (task_description or "").strip():
            return
        desc = task_description.strip()
        emb = embed_text(desc)
        blob = embedding_to_bytes(emb)
        key = hashlib.sha256(desc.encode("utf-8")).hexdigest()
        created_at = time.time()
        self.store.put_semantic(
            key=key,
            embedding_blob=blob,
            result=result,
            task_type=task_type or "general",
            original_description=desc,
            created_at=created_at,
        )
        self.index.add(emb, key, result, task_type or "general", created_at, desc)

    def invalidate(self, task_description: str) -> None:
        """Remove closest match above threshold."""
        from devsper.memory.embeddings import embed_text
        if not (task_description or "").strip():
            return
        query_emb = embed_text((task_description or "").strip())
        self.index.rebuild()
        hit = self.index.search(
            query_emb,
            threshold=self.threshold,
            max_age_seconds=-1,
        )
        if hit is None:
            return
        _sim, _result, _orig, _cached_at, _task_type, key = hit
        self.store.delete(key)
        self.index.rebuild()
