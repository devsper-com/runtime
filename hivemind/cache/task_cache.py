"""
Persistent task result cache. Before executing a task, hash(task) and check cache;
on hit return cached result. Store uses SQLite.
"""

import sqlite3
from pathlib import Path

from hivemind.types.task import Task
from hivemind.cache.hashing import task_hash


class TaskCache:
    """SQLite-backed cache: get(task) -> result or None, set(task, result)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(".hivemind") / "task_cache.db"
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
