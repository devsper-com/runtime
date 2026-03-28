from __future__ import annotations

from dataclasses import dataclass

from devsper.pool.config import PoolConfig
from devsper.pool.manager import PoolManager
from devsper.pool.store import InMemoryPoolStore


class BusStub:
    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    def publish(self, channel: str, payload: dict):
        self.published.append((channel, payload))


@dataclass
class PoolTestConfig(PoolConfig):
    profile: str = "local"
    max_tasks_per_minute: int = 60
    worker_timeout_secs: int = 90
    __test__ = False


async def make_pool() -> PoolManager:
    store = InMemoryPoolStore()
    bus = BusStub()
    cfg = PoolTestConfig()
    return PoolManager(store=store, bus=bus, config=cfg)

