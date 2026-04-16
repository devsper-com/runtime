"""Message bus: real pub/sub for task and agent events."""

from devsper.bus.message import BusMessage, create_bus_message
from devsper.bus.backends.base import BusBackend
from devsper.bus.backends.memory import InMemoryBus
from devsper.bus.backends.redis import RedisBus


def get_bus(config: object) -> BusBackend:
    """Return bus backend from config. Default InMemoryBus if bus config missing."""
    bus_cfg = getattr(config, "bus", None)
    backend = getattr(bus_cfg, "backend", "memory")
    if backend == "redis":
        redis_url = getattr(bus_cfg, "redis_url", "redis://localhost:6379")
        return RedisBus(redis_url=redis_url)
    if backend == "kafka":
        from devsper.bus.backends.kafka import KafkaBus
        kafka_cfg = getattr(bus_cfg, "kafka", None)
        bootstrap_servers = getattr(kafka_cfg, "bootstrap_servers", ["localhost:9092"])
        group_id = getattr(kafka_cfg, "group_id", "devsper-workers")
        client_id = getattr(kafka_cfg, "client_id", "devsper-bus")
        return KafkaBus(bootstrap_servers=bootstrap_servers, group_id=group_id, client_id=client_id)
    return InMemoryBus()


__all__ = [
    "get_bus",
    "MessageBus",
    "BusMessage",
    "BusBackend",
    "InMemoryBus",
    "RedisBus",
    "KafkaBus",
    "create_bus_message",
]

# Alias for spec
MessageBus = BusBackend
