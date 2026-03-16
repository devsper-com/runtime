"""Message bus: real pub/sub for task and agent events."""

from devsper.bus.message import BusMessage, create_bus_message
from devsper.bus.backends.base import BusBackend
from devsper.bus.backends.memory import InMemoryBus
from devsper.bus.backends.redis import RedisBus


def get_bus(config: object) -> BusBackend:
    """Return bus backend from config. Default InMemoryBus if bus config missing."""
    backend = getattr(getattr(config, "bus", None), "backend", "memory")
    if backend == "redis":
        redis_url = getattr(getattr(config, "bus", None), "redis_url", "redis://localhost:6379")
        return RedisBus(redis_url=redis_url)
    return InMemoryBus()


__all__ = [
    "get_bus",
    "MessageBus",
    "BusMessage",
    "BusBackend",
    "InMemoryBus",
    "RedisBus",
    "create_bus_message",
]

# Alias for spec
MessageBus = BusBackend
