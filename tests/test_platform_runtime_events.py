"""Mapping from devsper events to platform runtime event types."""

from datetime import datetime, timezone

from devsper.contracts.platform_event_type import PlatformEventType
from devsper.platform.runtime_events import map_devsper_event_to_platform
from devsper.types.event import Event, events


def test_map_run_lifecycle():
    t = datetime.now(timezone.utc)
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.SWARM_STARTED, payload={})) == PlatformEventType.RUN_STARTED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_STARTED, payload={"task_id": "a"})) == PlatformEventType.STEP_STARTED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_COMPLETED, payload={"task_id": "a"})) == PlatformEventType.STEP_COMPLETED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TOOL_CALLED, payload={})) == PlatformEventType.TOOL_CALLED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.RUN_COMPLETED, payload={})) == PlatformEventType.RUN_COMPLETED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.TASK_FAILED, payload={})) == PlatformEventType.RUN_FAILED


def test_map_agent_not_collapsed_to_step():
    t = datetime.now(timezone.utc)
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.AGENT_STARTED, payload={"task_id": "a"})) == PlatformEventType.AGENT_STARTED
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.AGENT_FINISHED, payload={"task_id": "a"})) == PlatformEventType.AGENT_FINISHED


def test_map_executor_finished():
    t = datetime.now(timezone.utc)
    assert map_devsper_event_to_platform(Event(timestamp=t, type=events.EXECUTOR_FINISHED, payload={})) == PlatformEventType.EXECUTOR_FINISHED


def test_map_worker_and_speculative():
    t = datetime.now(timezone.utc)
    assert (
        map_devsper_event_to_platform(Event(timestamp=t, type=events.WORKER_ASSIGNED, payload={}))
        == PlatformEventType.WORKER_ASSIGNED
    )
    assert (
        map_devsper_event_to_platform(Event(timestamp=t, type=events.SPECULATIVE_STARTED, payload={}))
        == PlatformEventType.SPECULATIVE_TASK_STARTED
    )
    assert (
        map_devsper_event_to_platform(Event(timestamp=t, type=events.SPECULATIVE_CANCELLED, payload={}))
        == PlatformEventType.SPECULATIVE_TASK_CANCELLED
    )


def test_map_clarification_events():
    t = datetime.now(timezone.utc)
    assert (
        map_devsper_event_to_platform(
            Event(timestamp=t, type=events.CLARIFICATION_REQUESTED, payload={})
        )
        == PlatformEventType.CLARIFICATION_REQUESTED
    )
    assert (
        map_devsper_event_to_platform(
            Event(timestamp=t, type=events.CLARIFICATION_RECEIVED, payload={})
        )
        == PlatformEventType.CLARIFICATION_ANSWERED
    )


def test_contract_constants_stable():
    assert PlatformEventType.AGENT_STARTED == "agent_started"
    assert PlatformEventType.AGENT_FINISHED == "agent_finished"
    assert PlatformEventType.WORKER_ASSIGNED == "WORKER_ASSIGNED"
