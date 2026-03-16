"""
Cache store backend for task cache. Holds exact-match and semantic (embedding) entries.
SQLite with optional BLOB column for embeddings; semantic entries use a separate table.
"""

import sqlite3
import time
from pathlib import Path
from typing import Protocol


class CacheStore(Protocol):
    """Protocol for cache storage (exact key or semantic)."""

    def get(self, key: str) -> tuple[str, float] | None:
        """Return (result, created_at) for key or None."""
        ...

    def set(self, key: str, result: str, created_at: float | None = None) -> None:
        """Store result for key."""
        ...

    def list_semantic_entries(self) -> list[tuple[bytes, str, str, float, str, str]]:
        """Return list of (embedding_blob, result, task_type, created_at, key, original_description)."""
        ...

    def put_semantic(
        self,
        key: str,
        embedding_blob: bytes,
        result: str,
        task_type: str,
        original_description: str,
        created_at: float | None = None,
    ) -> None:
        """Store a semantic cache entry."""
        ...

    def delete(self, key: str) -> None:
        """Remove entry by key."""
        ...

    def clear(self) -> None:
        """Remove all entries."""
        ...

    def stats(self) -> dict:
        """Return counts and optional semantic stats."""
        ...


def _default_db_path() -> Path:
    return Path(".devsper") / "task_cache.db"


class DefaultCacheStore:
    """
    SQLite-backed store: exact-match in task_cache; semantic in semantic_cache table.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
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
            c.execute("""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    key TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    result TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    original_description TEXT NOT NULL
                )
            """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_semantic_task_type ON semantic_cache(task_type)"
            )

    def get(self, key: str) -> tuple[str, float] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT result, created_at FROM task_cache WHERE key = ?", (key,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def set(self, key: str, result: str, created_at: float | None = None) -> None:
        ts = created_at if created_at is not None else time.time()
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO task_cache (key, result, created_at) VALUES (?, ?, ?)",
                (key, result, ts),
            )

    def list_semantic_entries(
        self,
    ) -> list[tuple[bytes, str, str, float, str, str]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT embedding, result, task_type, created_at, key, original_description FROM semantic_cache"
            ).fetchall()
        return list(rows)

    def put_semantic(
        self,
        key: str,
        embedding_blob: bytes,
        result: str,
        task_type: str,
        original_description: str,
        created_at: float | None = None,
    ) -> None:
        ts = created_at if created_at is not None else time.time()
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO semantic_cache
                   (key, embedding, result, task_type, created_at, original_description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (key, embedding_blob, result, task_type, ts, original_description),
            )

    def delete(self, key: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM task_cache WHERE key = ?", (key,))
            c.execute("DELETE FROM semantic_cache WHERE key = ?", (key,))

    def clear(self) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM task_cache")
            c.execute("DELETE FROM semantic_cache")

    def stats(self) -> dict:
        with self._conn() as c:
            exact = c.execute("SELECT COUNT(*) FROM task_cache").fetchone()[0]
            semantic = c.execute("SELECT COUNT(*) FROM semantic_cache").fetchone()[0]
        return {"entries": exact, "semantic_entries": semantic }


def get_default_cache_store(db_path: str | Path | None = None) -> DefaultCacheStore:
    """Return the default cache store (same DB path as TaskCache)."""
    return DefaultCacheStore(db_path=db_path)
