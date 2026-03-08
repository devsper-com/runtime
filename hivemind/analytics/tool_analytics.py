"""
Track tool usage: count, success rate, latency. Persist in SQLite.
"""

import sqlite3
import time
from pathlib import Path


class ToolAnalytics:
    """SQLite-backed analytics for tool usage: count, success rate, latency."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(".hivemind") / "tool_analytics.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tool_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_usage_name ON tool_usage(tool_name)"
            )

    def record(self, tool_name: str, success: bool, latency_ms: float) -> None:
        """Record one tool invocation."""
        with self._conn() as c:
            c.execute(
                "INSERT INTO tool_usage (tool_name, success, latency_ms, created_at) VALUES (?, ?, ?, ?)",
                (tool_name, 1 if success else 0, latency_ms, time.time()),
            )

    def get_stats(self) -> list[dict]:
        """Return per-tool stats: name, count, success_rate, avg_latency_ms."""
        with self._conn() as c:
            rows = c.execute("""
                SELECT tool_name,
                       COUNT(*) AS cnt,
                       SUM(success) AS ok,
                       AVG(latency_ms) AS avg_ms
                FROM tool_usage
                GROUP BY tool_name
                ORDER BY cnt DESC
                """).fetchall()
        return [
            {
                "tool_name": r[0],
                "count": r[1],
                "success_count": r[2],
                "success_rate": (r[2] / r[1] * 100.0) if r[1] else 0.0,
                "avg_latency_ms": round(r[3], 2) if r[3] is not None else 0.0,
            }
            for r in rows
        ]


_default: ToolAnalytics | None = None


def get_default_analytics() -> ToolAnalytics:
    """Return the default analytics instance (singleton)."""
    global _default
    if _default is None:
        _default = ToolAnalytics()
    return _default
