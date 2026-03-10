"""In-memory asyncio bus backend. Single-node, zero config."""

import asyncio
import fnmatch
from typing import Awaitable, Callable

from hivemind.bus.message import BusMessage
from hivemind.bus.backends.base import BusBackend


def _topic_matches(pattern: str, topic: str) -> bool:
    """Return True if topic matches pattern (supports * wildcard)."""
    if pattern == topic:
        return True
    if "*" in pattern:
        return fnmatch.fnmatch(topic, pattern)
    return False


class InMemoryBus(BusBackend):
    """Asyncio-based in-memory bus. Dict of topic pattern -> list of handler coroutines."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[BusMessage], Awaitable[None]]]] = {}
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False
        self._handlers.clear()

    async def publish(self, message: BusMessage) -> None:
        topic = message.topic
        to_call: list[Awaitable[None]] = []
        for pattern, handlers in self._handlers.items():
            if _topic_matches(pattern, topic):
                for h in handlers:
                    to_call.append(h(message))
        if to_call:
            await asyncio.gather(*to_call)

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[BusMessage], Awaitable[None]],
        run_id: str | None = None,
    ) -> None:
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    async def unsubscribe(self, topic: str) -> None:
        self._handlers.pop(topic, None)
