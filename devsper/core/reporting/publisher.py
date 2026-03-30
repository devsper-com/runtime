from __future__ import annotations

import queue
import threading
from typing import Protocol

from devsper.types.event import Event


class EventSink(Protocol):
    def publish(self, event: Event) -> None: ...


class EventPublisher:
    """Non-blocking fanout publisher to multiple sinks."""

    def __init__(self, sinks: list[EventSink], queue_size: int = 1024) -> None:
        self._sinks = list(sinks)
        self._q: queue.Queue[Event] = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="event-publisher")
        self._thread.start()

    def publish(self, event: Event) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            # Drop oldest semantics are safer than blocking execution.
            try:
                _ = self._q.get_nowait()
            except queue.Empty:
                return
            try:
                self._q.put_nowait(event)
            except queue.Full:
                return

    def close(self, timeout_s: float = 2.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout_s)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            for sink in self._sinks:
                try:
                    sink.publish(event)
                except Exception:
                    continue

