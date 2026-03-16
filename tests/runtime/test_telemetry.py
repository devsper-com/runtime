"""Tests for execution telemetry collection from event log."""

import tempfile
import os
from datetime import datetime, timezone, timedelta

from devsper.types.event import Event, events
from devsper.runtime.telemetry import collect_telemetry, print_telemetry_summary


def test_telemetry_empty_path():
    m = collect_telemetry("/nonexistent/events.jsonl")
    assert m["tasks_completed"] == 0
    assert m["tasks_failed"] == 0
    assert m["max_concurrency"] == 0
    assert m["task_success_rate"] == 0.0


def test_telemetry_collects_task_duration_and_concurrency():
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(seconds=2)
    t2 = t0 + timedelta(seconds=3)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for ev in [
            Event(timestamp=t0, type=events.TASK_STARTED, payload={"task_id": "task_1"}),
            Event(timestamp=t0, type=events.AGENT_STARTED, payload={"task_id": "task_1"}),
            Event(timestamp=t1, type=events.AGENT_FINISHED, payload={"task_id": "task_1"}),
            Event(timestamp=t2, type=events.TASK_COMPLETED, payload={"task_id": "task_1"}),
        ]:
            f.write(ev.model_dump_json() + "\n")
        path = f.name

    try:
        m = collect_telemetry(path)
        assert m["tasks_completed"] == 1
        assert m["tasks_failed"] == 0
        assert m["avg_task_duration_seconds"] == 3.0
        assert m["avg_agent_latency_seconds"] == 2.0
        assert m["max_concurrency"] == 1
        assert m["task_success_rate"] == 1.0
    finally:
        os.unlink(path)


def test_print_telemetry_summary():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        t = datetime.now(timezone.utc)
        e = Event(timestamp=t, type=events.TASK_COMPLETED, payload={"task_id": "t1"})
        f.write(e.model_dump_json() + "\n")
        path = f.name

    try:
        out = print_telemetry_summary(path)
        assert "tasks_completed" in out
        assert "avg_task_time" in out or "avg_agent_latency" in out
    finally:
        os.unlink(path)
