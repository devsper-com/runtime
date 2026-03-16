"""Tests for swarm execution replay from event log."""

import tempfile
import os
from datetime import datetime, timezone

from devsper.types.event import Event, events
from devsper.runtime.replay import replay_execution, _load_events


def test_replay_empty_path_returns_no_events():
    out = replay_execution("/nonexistent/path/events.jsonl")
    assert "No events found" in out


def test_replay_loads_and_prints_ordered_events():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        t = datetime.now(timezone.utc)
        for ev_type, payload in [
            (events.PLANNER_STARTED, {"task_id": "root"}),
            (events.TASK_CREATED, {"task_id": "task_1", "description": "Step 1"}),
            (events.TASK_CREATED, {"task_id": "task_2", "description": "Step 2"}),
            (events.AGENT_STARTED, {"task_id": "task_1"}),
            (events.TASK_STARTED, {"task_id": "task_1"}),
            (events.TASK_COMPLETED, {"task_id": "task_1"}),
            (events.AGENT_FINISHED, {"task_id": "task_1"}),
        ]:
            e = Event(timestamp=t, type=ev_type, payload=payload)
            f.write(e.model_dump_json() + "\n")
        path = f.name

    try:
        out = replay_execution(path)
        assert "[planner_started]" in out
        assert "task_1" in out
        assert "task_2" in out
        assert "[agent_started]" in out
        assert "[task_completed]" in out
    finally:
        os.unlink(path)


def test_load_events_returns_list():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        t = datetime.now(timezone.utc)
        e = Event(timestamp=t, type=events.SWARM_STARTED, payload={"user_task": "test"})
        f.write(e.model_dump_json() + "\n")
        path = f.name

    try:
        loaded = _load_events(path)
        assert len(loaded) == 1
        assert loaded[0].type == events.SWARM_STARTED
    finally:
        os.unlink(path)
