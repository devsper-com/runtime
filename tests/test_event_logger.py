from datetime import datetime, timezone
from hivemind.utils.event_logger import EventLog
from hivemind.types.event import Event, events

log = EventLog()
log.clear()

log.append_event(Event(timestamp=datetime.now(timezone.utc), type=events.SWARM_STARTED, payload={"swarm_id": "1"}))
log.append_event(Event(timestamp=datetime.now(timezone.utc), type=events.TASK_CREATED, payload={"task_id": "1"}))
log.append_event(Event(timestamp=datetime.now(timezone.utc), type=events.TASK_STARTED, payload={"task_id": "1"}))
log.append_event(Event(timestamp=datetime.now(timezone.utc), type=events.AGENT_STARTED, payload={"agent_id": "1", "task_id": "1"}))
log.append_event(Event(timestamp=datetime.now(timezone.utc), type=events.TASK_COMPLETED, payload={"task_id": "1"}))

for event in log.read_events():
    print(event)