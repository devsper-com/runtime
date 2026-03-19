from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from devsper.export.service import ExportOptions, export_all_runs
from devsper.runtime.run_history import RunHistory


def _write_event(path: Path, event_type: str, payload: dict, ts: str) -> None:
    row = {"timestamp": ts, "type": event_type, "payload": payload}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def test_export_all_runs_generates_formats(tmp_path: Path):
    db_path = tmp_path / "runs.db"
    ev_path = tmp_path / "run_1.jsonl"

    _write_event(ev_path, "swarm_started", {"user_task": "Research swarm intelligence"}, "2026-01-01T00:00:00+00:00")
    _write_event(ev_path, "tool_called", {"task_id": "t1", "tool": "arxiv_search"}, "2026-01-01T00:00:01+00:00")
    _write_event(ev_path, "clarification_needed", {"request_id": "q1", "task_id": "t1", "question": "Which source?"}, "2026-01-01T00:00:02+00:00")
    _write_event(ev_path, "clarification_received", {"request_id": "q1", "answers": {"Which source?": "arXiv"}}, "2026-01-01T00:00:03+00:00")
    _write_event(ev_path, "task_completed", {"task_id": "t1", "result": "See DOI 10.1000/xyz123 and https://arxiv.org/abs/2401.00001"}, "2026-01-01T00:00:04+00:00")
    _write_event(ev_path, "swarm_finished", {}, "2026-01-01T00:00:05+00:00")

    RunHistory(db_path=db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, root_task, strategy, started_at, finished_at,
                duration_seconds, total_tasks, completed_tasks, failed_tasks,
                estimated_cost_usd, models_used, events_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run_1",
                "Research swarm intelligence",
                "research",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:05+00:00",
                5.0,
                1,
                1,
                0,
                0.12,
                json.dumps(["gpt-5-mini"]),
                str(ev_path),
            ),
        )

    out_dir = tmp_path / "exports"
    manifest = export_all_runs(
        ExportOptions(output_dir=str(out_dir), pdf_pipeline="both", db_path=str(db_path))
    )

    assert manifest["run_count"] == 1
    assert (out_dir / "manifest.json").is_file()
    assert (out_dir / "history.json").is_file()
    assert (out_dir / "all_runs.md").is_file()
    assert (out_dir / "all_runs.rst").is_file()
    assert (out_dir / "all_runs.tex").is_file()
    assert (out_dir / "all_runs.bib").is_file()
    assert (out_dir / "all_runs.html").is_file()
    assert (out_dir / "runs" / "run_1.md").is_file()

    md = (out_dir / "runs" / "run_1.md").read_text(encoding="utf-8")
    assert "Clarification history" in md
    assert "Which source?" in md
    assert "10.1000/xyz123" in md
    all_md = (out_dir / "all_runs.md").read_text(encoding="utf-8")
    assert "Run Details" in all_md
    assert "Timeline events" in all_md


def test_export_resolves_relative_events_path(tmp_path: Path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    events_dir = runtime_root / ".devsper" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    ev_path = events_dir / "run_rel.jsonl"
    _write_event(ev_path, "swarm_started", {"user_task": "Relative path test"}, "2026-01-01T00:00:00+00:00")
    _write_event(ev_path, "tool_called", {"task_id": "t1", "tool": "search_files"}, "2026-01-01T00:00:01+00:00")
    _write_event(ev_path, "swarm_finished", {}, "2026-01-01T00:00:02+00:00")

    db_path = tmp_path / "runs.db"
    RunHistory(db_path=db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, root_task, strategy, started_at, finished_at,
                duration_seconds, total_tasks, completed_tasks, failed_tasks,
                estimated_cost_usd, models_used, events_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run_rel",
                "Relative path test",
                "research",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:02+00:00",
                2.0,
                1,
                1,
                0,
                None,
                "[]",
                ".devsper/events/run_rel.jsonl",
            ),
        )

    monkeypatch.chdir(runtime_root)
    out_dir = tmp_path / "exports_rel"
    manifest = export_all_runs(
        ExportOptions(output_dir=str(out_dir), pdf_pipeline="html", db_path=str(db_path))
    )
    assert manifest["run_count"] == 1
    run_md = (out_dir / "runs" / "run_rel.md").read_text(encoding="utf-8")
    assert "search_files" in run_md
    assert "## Timeline" in run_md
