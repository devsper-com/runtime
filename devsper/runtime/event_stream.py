from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from devsper.types.event import Event, events
from devsper.utils.event_logger import EventLog


@dataclass
class RuntimeEvent:
    type: events
    payload: dict[str, Any]
    at: datetime


class RuntimeEventStream:
    """In-process async event stream backed by EventLog."""

    def __init__(self, event_log: EventLog, max_queue_size: int = 2048) -> None:
        self._event_log = event_log
        self._queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue(maxsize=max(1, int(max_queue_size)))
        self._closed = False
        self._dropped = 0

    async def publish(self, event_type: events, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        now = datetime.now(timezone.utc)
        self._event_log.append_event(Event(timestamp=now, type=event_type, payload=payload))
        evt = RuntimeEvent(type=event_type, payload=payload, at=now)
        try:
            self._queue.put_nowait(evt)
        except asyncio.QueueFull:
            # Backpressure policy: drop oldest event and keep newest.
            try:
                _ = self._queue.get_nowait()
                self._dropped += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(evt)
            except asyncio.QueueFull:
                self._dropped += 1

    async def subscribe(self) -> AsyncIterator[RuntimeEvent]:
        while not self._closed:
            yield await self._queue.get()

    def close(self) -> None:
        self._closed = True

    @property
    def dropped_events(self) -> int:
        return self._dropped

