"""Tests for deterministic replay engine."""

import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone

from devsper.types.event import Event, events
from devsper.runtime.replay_engine import (
    replay_run,
    list_run_ids,
    _find_log_path,
    _load_events,
)


def test_find_log_path_missing_dir():
    assert _find_log_path("/nonexistent", "any_run") is None


def test_load_events_empty_path():
    assert _load_events("/nonexistent/file.jsonl") == []


def test_replay_run_nonexistent_run_id():
    with tempfile.TemporaryDirectory() as d:
        out = replay_run("nonexistent_run_id", events_dir=d)
    assert "No event log found" in out


def test_replay_run_empty_log():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "myrun.jsonl"
        path.write_text("")
        out = replay_run("myrun", events_dir=d)
    assert "Empty event log" in out


def test_replay_run_reconstructs_timeline():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "run1.jsonl"
        t = datetime.now(timezone.utc)
        lines = []
        for ev_type, payload in [
            (events.SWARM_STARTED, {"user_task": "test task"}),
            (events.PLANNER_STARTED, {"task_id": "root"}),
            (events.TASK_CREATED, {"task_id": "t1", "description": "Step 1"}),
            (events.PLANNER_FINISHED, {"subtask_count": 1}),
            (events.EXECUTOR_STARTED, {}),
            (events.AGENT_STARTED, {"task_id": "t1"}),
            (events.TASK_COMPLETED, {"task_id": "t1"}),
            (events.SWARM_FINISHED, {"task_count": 1}),
        ]:
            e = Event(timestamp=t, type=ev_type, payload=payload)
            lines.append(e.model_dump_json() + "\n")
        path.write_text("".join(lines))
        out = replay_run("run1", events_dir=d)
    assert "SWARM_STARTED" in out
    assert "PLANNER_STARTED" in out
    assert "TASK_CREATED" in out
    assert "task_id=t1" in out
    assert "SWARM_FINISHED" in out


def test_list_run_ids():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.jsonl").write_text("")
        (Path(d) / "b.jsonl").write_text("")
        ids_ = list_run_ids(d)
    assert "a" in ids_
    assert "b" in ids_
