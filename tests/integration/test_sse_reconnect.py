from datetime import datetime, timezone

from devsper.types.event import Event, events


def test_event_contains_replay_fields_for_sse_reconnect():
    ev = Event(
        timestamp=datetime.now(timezone.utc),
        type=events.CLARIFICATION_REQUESTED,
        payload={"request_id": "req-1", "task_id": "task-1"},
    )
    d = ev.to_dict()
    assert d.get("event_id")
    # sequence_id may be assigned later by EventLog/platform sink; should still be serializable.
    assert "sequence_id" in d

