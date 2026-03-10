"""Abstract base for message bus backends."""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from hivemind.bus.message import BusMessage


class BusBackend(ABC):
    @abstractmethod
    async def publish(self, message: BusMessage) -> None:
        """Publish a message to the bus."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[BusMessage], Awaitable[None]],
        run_id: str | None = None,
    ) -> None:
        """Subscribe to a topic (supports wildcards like task.*). run_id scopes channel when set (Redis)."""
        ...

    @abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the backend (e.g. connect to Redis)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the backend."""
        ...
