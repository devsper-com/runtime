import asyncio
import os
from datetime import datetime, timezone
import logging

from devsper.core.reporting import EventPublisher
from devsper.types.event import Event, events


# Map Event types to bus topics (v1.9). Unmapped events use event.<type_value>.
EVENT_TO_TOPIC = {
    events.TASK_STARTED: "task.started",
    events.TASK_COMPLETED: "task.completed",
    events.TASK_FAILED: "task.failed",
    events.TASK_CREATED: "task.ready",
    events.AGENT_BROADCAST: "agent.broadcast",
    events.SWARM_STARTED: "swarm.control",
    events.SWARM_FINISHED: "swarm.control",
    events.AGENT_STARTED: "agent.broadcast",
    events.AGENT_FINISHED: "agent.broadcast",
    events.EXECUTOR_STARTED: "swarm.control",
    events.EXECUTOR_FINISHED: "swarm.control",
}


def _event_to_bus_topic(event_type: events) -> str:
    return EVENT_TO_TOPIC.get(event_type, f"event.{event_type.value}")


class EventLog:
    def __init__(
        self,
        events_folder_path: str = ".devsper/events",
        bus: object = None,
        run_id: str | None = None,
        platform_sink: object | None = None,
    ):
        os.makedirs(events_folder_path, exist_ok=True)
        self.log_path = os.path.join(
            events_folder_path, f"events_{datetime.now(timezone.utc)}.jsonl"
        )
        self._bus = bus
        self._run_id = run_id
        self._platform_sink = platform_sink
        sinks = []
        if self._bus is not None:
            sinks.append(_BusSink(self))
        if self._platform_sink is not None:
            sinks.append(_PlatformSink(self._platform_sink))
        self._publisher = EventPublisher(sinks) if sinks else None
        self._seq = 0
        self._log = logging.getLogger(__name__)

    @property
    def run_id(self) -> str:
        """Identifier for this run (basename of log file without extension)."""
        if self._run_id is not None:
            return self._run_id
        return os.path.basename(self.log_path).replace(".jsonl", "")

    def append_event(self, event: Event) -> None:
        # Assign per-run monotonic sequence for local ordering/replay hints.
        if event.sequence_id is None:
            self._seq += 1
            event.sequence_id = self._seq
        with open(self.log_path, "a") as f:
            f.write(event.model_dump_json() + "\n")
        self._log.debug(
            "event appended run_id=%s event_id=%s sequence_id=%s type=%s",
            self.run_id,
            event.event_id,
            event.sequence_id,
            event.type.value if hasattr(event.type, "value") else str(event.type),
        )
        if self._publisher is not None:
            self._publisher.publish(event)

    def _publish_to_bus(self, event: Event) -> None:
        try:
            from devsper.bus.message import create_bus_message
            topic = _event_to_bus_topic(event.type)
            payload = event.to_dict()
            msg = create_bus_message(
                topic=topic,
                payload=payload,
                run_id=getattr(self, "run_id", "") or "",
            )
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            if loop is not None:
                loop.create_task(self._bus.publish(msg))
            else:
                try:
                    asyncio.run(self._bus.publish(msg))
                except Exception:
                    pass
        except Exception:
            pass

    def read_events(self) -> list[Event]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path, "r") as f:
            return [Event.model_validate_json(line) for line in f if line.strip()]

    def clear(self) -> None:
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def append_run_manifest(self, manifest: dict) -> None:
        try:
            event = Event(
                timestamp=datetime.now(timezone.utc),
                type=events.RUN_MANIFEST_EMITTED,
                payload={"manifest_version": "1", "manifest": manifest},
            )
            self.append_event(event)
        except Exception:
            pass


class _BusSink:
    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log

    def publish(self, event: Event) -> None:
        self._event_log._publish_to_bus(event)


class _PlatformSink:
    def __init__(self, sink: object) -> None:
        self._sink = sink

    def publish(self, event: Event) -> None:
        on = getattr(self._sink, "on_devsper_event", None)
        if callable(on):
            on(event)
