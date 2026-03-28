"""Mapping from devsper events to platform runtime event types."""

from datetime import datetime, timezone

from devsper.platform.runtime_events import map_devsper_event_to_platform
from devsper.types.event import Event, events


def test_map_run_lifecycle():
    t = datetime.now(timezone.utc)
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.SWARM_STARTED, payload={})) == "run_started"
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_STARTED, payload={"task_id": "a"})) == "step_started"
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_COMPLETED, payload={"task_id": "a"})) == "step_completed"
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TOOL_CALLED, payload={})) == "run_progress"
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.RUN_COMPLETED, payload={})) == "run_completed"
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_FAILED, payload={})) == "run_failed"


def test_map_unknown_is_none():
    t = datetime.now(timezone.utc)
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.EXECUTOR_FINISHED, payload={})) is None
