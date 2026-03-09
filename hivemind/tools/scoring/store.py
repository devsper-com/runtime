"""
Persistent score store for tool reliability (SQLite at ~/.config/hivemind/tool_scores.db).
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _default_db_path() -> Path:
    p = Path.home() / ".config" / "hivemind" / "tool_scores.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class ToolScore:
    tool_name: str
    success_rate: float  # 0.0–1.0
    avg_latency_ms: float
    p95_latency_ms: float
    total_calls: int
    recent_failures: int
    composite_score: float  # final blended score
    last_updated: str
    is_new: bool  # True if total_calls < 5 (no penalty for new tools)


class ToolScoreStore:
    """SQLite-backed store for tool results and materialized tool_scores."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tool_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    task_type TEXT,
                    success INTEGER NOT NULL,
                    latency_ms INTEGER,
                    error_type TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tool_scores (
                    tool_name TEXT PRIMARY KEY,
                    success_rate REAL,
                    avg_latency_ms REAL,
                    p95_latency_ms REAL,
                    total_calls INTEGER,
                    recent_failures INTEGER,
                    composite_score REAL,
                    last_updated TEXT
                )
            """)
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_results_name ON tool_results(tool_name)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_tool_results_ts ON tool_results(timestamp)"
            )

    def record(
        self,
        tool_name: str,
        task_type: str | None,
        success: bool,
        latency_ms: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """Insert one result and recompute/upsert tool_scores for this tool."""
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO tool_results
                   (tool_name, task_type, success, latency_ms, error_type, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    tool_name,
                    task_type or "general",
                    1 if success else 0,
                    latency_ms,
                    error_type,
                    ts,
                ),
            )
        self._recompute_scores(tool_name)

    def _recompute_scores(self, tool_name: str) -> None:
        from hivemind.tools.scoring.scorer import compute_composite_score

        with self._conn() as c:
            rows = c.execute(
                """SELECT success, latency_ms
                   FROM tool_results
                   WHERE tool_name = ?
                   ORDER BY id DESC""",
                (tool_name,),
            ).fetchall()
        if not rows:
            return
        total = len(rows)
        successes = sum(1 for r in rows if r[0] == 1)
        success_rate = successes / total if total else 0.0
        latencies = [r[1] for r in rows if r[1] is not None]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0
        if latencies:
            sorted_lat = sorted(latencies)
            idx = max(0, int(len(sorted_lat) * 0.95) - 1)
            p95_latency_ms = sorted_lat[idx]
        else:
            p95_latency_ms = 0.0
        recent_20 = rows[:20]
        recent_failures = sum(1 for r in recent_20 if r[0] == 0)
        stats = {
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency_ms,
            "p95_latency_ms": p95_latency_ms,
            "total_calls": total,
            "recent_failures": recent_failures,
        }
        composite = compute_composite_score(stats)
        with self._conn() as c2:
            r = c2.execute(
                "SELECT timestamp FROM tool_results WHERE tool_name = ? ORDER BY id DESC LIMIT 1",
                (tool_name,),
            ).fetchone()
        last_ts = r[0] if r else datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO tool_scores
                   (tool_name, success_rate, avg_latency_ms, p95_latency_ms,
                    total_calls, recent_failures, composite_score, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(tool_name) DO UPDATE SET
                     success_rate = excluded.success_rate,
                     avg_latency_ms = excluded.avg_latency_ms,
                     p95_latency_ms = excluded.p95_latency_ms,
                     total_calls = excluded.total_calls,
                     recent_failures = excluded.recent_failures,
                     composite_score = excluded.composite_score,
                     last_updated = excluded.last_updated""",
                (
                    tool_name,
                    success_rate,
                    avg_latency_ms,
                    p95_latency_ms,
                    total,
                    recent_failures,
                    composite,
                    last_ts,
                ),
            )

    def get_score(self, tool_name: str) -> ToolScore | None:
        row = None
        with self._conn() as c:
            row = c.execute(
                "SELECT tool_name, success_rate, avg_latency_ms, p95_latency_ms,"
                " total_calls, recent_failures, composite_score, last_updated"
                " FROM tool_scores WHERE tool_name = ?",
                (tool_name,),
            ).fetchone()
        if not row:
            return None
        return ToolScore(
            tool_name=row[0],
            success_rate=row[1],
            avg_latency_ms=row[2],
            p95_latency_ms=row[3],
            total_calls=row[4],
            recent_failures=row[5],
            composite_score=row[6],
            last_updated=row[7],
            is_new=row[4] < 5,
        )

    def get_all_scores(self) -> list[ToolScore]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT tool_name, success_rate, avg_latency_ms, p95_latency_ms,
                          total_calls, recent_failures, composite_score, last_updated
                   FROM tool_scores
                   ORDER BY composite_score DESC"""
            ).fetchall()
        return [
            ToolScore(
                tool_name=r[0],
                success_rate=r[1],
                avg_latency_ms=r[2],
                p95_latency_ms=r[3],
                total_calls=r[4],
                recent_failures=r[5],
                composite_score=r[6],
                last_updated=r[7],
                is_new=r[4] < 5,
            )
            for r in rows
        ]

    def get_scores_for_tools(self, tool_names: list[str]) -> dict[str, ToolScore]:
        result: dict[str, ToolScore] = {}
        for name in tool_names:
            s = self.get_score(name)
            if s is not None:
                result[name] = s
        return result

    def reset(self, tool_name: str | None) -> None:
        """Delete all records for a tool (or all tools if tool_name is None)."""
        with self._conn() as c:
            if tool_name is None:
                c.execute("DELETE FROM tool_results")
                c.execute("DELETE FROM tool_scores")
            else:
                c.execute("DELETE FROM tool_results WHERE tool_name = ?", (tool_name,))
                c.execute("DELETE FROM tool_scores WHERE tool_name = ?", (tool_name,))

    def prune(self, days: int = 90) -> int:
        """Delete results older than N days. Returns number of rows deleted."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as c:
            cur = c.execute("DELETE FROM tool_results WHERE timestamp < ?", (cutoff,))
            deleted = cur.rowcount
        # Recompute scores for tools that still have results; drop scores for tools with no results left
        with self._conn() as c:
            remaining = {
                r[0] for r in c.execute("SELECT DISTINCT tool_name FROM tool_results").fetchall()
            }
            all_scored = [
                r[0] for r in c.execute("SELECT tool_name FROM tool_scores").fetchall()
            ]
        for name in all_scored:
            if name in remaining:
                self._recompute_scores(name)
            else:
                with self._conn() as c:
                    c.execute("DELETE FROM tool_scores WHERE tool_name = ?", (name,))
        return deleted

    def result_count(self) -> int:
        """Total number of result rows (for doctor)."""
        with self._conn() as c:
            r = c.execute("SELECT COUNT(*) FROM tool_results").fetchone()
        return r[0] if r else 0

    def tool_count(self) -> int:
        """Number of tools with scores (for doctor)."""
        with self._conn() as c:
            r = c.execute("SELECT COUNT(*) FROM tool_scores").fetchone()
        return r[0] if r else 0
