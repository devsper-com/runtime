"""
Persistent run history: SQLite DB at ~/.config/devsper/runs.db.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from devsper.intelligence.analysis.run_report import RunReport


HISTORY_DB = Path("~/.config/devsper/runs.db").expanduser()


@dataclass
class RunRow:
    run_id: str
    root_task: str
    strategy: str
    started_at: str
    finished_at: str
    duration_seconds: float
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    estimated_cost_usd: float | None
    models_used: str  # JSON array string
    events_path: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    root_task TEXT,
    strategy TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    total_tasks INTEGER,
    completed_tasks INTEGER,
    failed_tasks INTEGER,
    estimated_cost_usd REAL,
    models_used TEXT,
    events_path TEXT
);
"""


def _ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(_SCHEMA)


class RunHistory:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or HISTORY_DB
        _ensure_db(self._db)

    def record_run(self, report: RunReport) -> None:
        """Persist report to DB. Called at SWARM_FINISHED."""
        events_path = ""
        try:
            from devsper.config import get_config
            cfg = get_config()
            events_dir = Path(cfg.events_dir)
            candidate = events_dir / f"{report.run_id}.jsonl"
            if candidate.is_file():
                events_path = str(candidate)
            else:
                for f in events_dir.glob("*.jsonl"):
                    if f.stem == report.run_id:
                        events_path = str(f)
                        break
        except Exception:
            pass
        models_used_json = json.dumps(report.models_used or [])
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, root_task, strategy, started_at, finished_at,
                    duration_seconds, total_tasks, completed_tasks, failed_tasks,
                    estimated_cost_usd, models_used, events_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    report.root_task,
                    report.strategy,
                    report.started_at,
                    report.finished_at,
                    report.total_duration_seconds,
                    report.total_tasks,
                    report.completed_tasks,
                    report.failed_tasks,
                    report.estimated_cost_usd,
                    models_used_json,
                    events_path,
                ),
            )

    def list_runs(
        self,
        limit: int = 20,
        filter_status: str | None = None,
    ) -> list[RunRow]:
        """filter_status: 'failed' to only return runs with failed_tasks > 0."""
        with sqlite3.connect(str(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            if filter_status == "failed":
                cur = conn.execute(
                    """
                    SELECT run_id, root_task, strategy, started_at, finished_at,
                           duration_seconds, total_tasks, completed_tasks, failed_tasks,
                           estimated_cost_usd, models_used, events_path
                    FROM runs WHERE failed_tasks > 0
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT run_id, root_task, strategy, started_at, finished_at,
                           duration_seconds, total_tasks, completed_tasks, failed_tasks,
                           estimated_cost_usd, models_used, events_path
                    FROM runs ORDER BY started_at DESC LIMIT ?
                    """,
                    (limit,),
                )
            rows = cur.fetchall()
        return [_row_to_run(dict(r)) for r in rows]

    def get_run(self, run_id: str) -> RunRow | None:
        with sqlite3.connect(str(self._db)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT run_id, root_task, strategy, started_at, finished_at, "
                "duration_seconds, total_tasks, completed_tasks, failed_tasks, "
                "estimated_cost_usd, models_used, events_path FROM runs WHERE run_id = ?",
                (run_id,),
            )
            row = cur.fetchone()
        return _row_to_run(dict(row)) if row else None

    def delete_run(self, run_id: str) -> None:
        """Remove from DB and delete the events file if path is stored."""
        row = self.get_run(run_id)
        with sqlite3.connect(str(self._db)) as conn:
            conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        if row and row.events_path and Path(row.events_path).is_file():
            try:
                Path(row.events_path).unlink()
            except OSError:
                pass

    def get_stats(self) -> dict:
        """Aggregate: total runs, avg duration, total cost, most-used strategy."""
        with sqlite3.connect(str(self._db)) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) as n, AVG(duration_seconds) as avg_dur, "
                "SUM(estimated_cost_usd) as total_cost FROM runs"
            )
            row = cur.fetchone()
            n = row[0] or 0
            avg_dur = row[1] or 0.0
            total_cost = row[2] or 0.0
            cur2 = conn.execute(
                "SELECT strategy, COUNT(*) as c FROM runs GROUP BY strategy ORDER BY c DESC LIMIT 1"
            )
            strat_row = cur2.fetchone()
            most_used_strategy = strat_row[0] if strat_row else ""
        return {
            "total_runs": n,
            "avg_duration_seconds": round(avg_dur, 2),
            "total_estimated_cost_usd": round(total_cost, 4) if total_cost else 0.0,
            "most_used_strategy": most_used_strategy,
        }


def _row_to_run(d: dict) -> RunRow:
    models_raw = d.get("models_used") or "[]"
    try:
        _ = json.loads(models_raw)
    except Exception:
        models_raw = "[]"
    return RunRow(
        run_id=d["run_id"],
        root_task=d.get("root_task") or "",
        strategy=d.get("strategy") or "",
        started_at=d.get("started_at") or "",
        finished_at=d.get("finished_at") or "",
        duration_seconds=float(d.get("duration_seconds") or 0),
        total_tasks=int(d.get("total_tasks") or 0),
        completed_tasks=int(d.get("completed_tasks") or 0),
        failed_tasks=int(d.get("failed_tasks") or 0),
        estimated_cost_usd=d.get("estimated_cost_usd") if d.get("estimated_cost_usd") is not None else None,
        models_used=models_raw,
        events_path=d.get("events_path") or "",
    )
