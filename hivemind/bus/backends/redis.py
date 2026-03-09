"""Redis pub/sub bus backend."""

import asyncio
from typing import Awaitable, Callable

from hivemind.bus.message import BusMessage
from hivemind.bus.backends.base import BusBackend
from hivemind.types.exceptions import BusConnectionError


class RedisBus(BusBackend):
    """Redis pub/sub backend. Lazy import redis.asyncio."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._pub: object = None
        self._sub: object = None
        self._pubsub: object = None
        self._handlers: dict[str, list[Callable[[BusMessage], Awaitable[None]]]] = {}
        self._listen_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ImportError(
                "Redis bus requires redis package. Install with: pip install redis"
            ) from e
        try:
            self._pub = aioredis.from_url(self._redis_url)
            self._sub = aioredis.from_url(self._redis_url)
            self._pubsub = self._sub.pubsub()
            await self._pub.ping()
        except Exception as e:
            raise BusConnectionError(
                f"Cannot connect to Redis at {self._redis_url}: {e}"
            ) from e
        self._running = True

    @property
    def redis_client(self) -> object:
        """Redis connection for cluster registry/election/state (v1.10)."""
        return self._pub

    async def stop(self) -> None:
        self._running = False
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None
        if self._pub is not None:
            try:
                await self._pub.aclose()
            except Exception:
                pass
            self._pub = None
        if self._sub is not None:
            try:
                await self._sub.aclose()
            except Exception:
                pass
            self._sub = None
        self._handlers.clear()

    async def publish(self, message: BusMessage) -> None:
        if self._pub is None:
            raise BusConnectionError("Redis bus not started. Call start() first.")
        await self._pub.publish(message.topic, message.to_json())

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[BusMessage], Awaitable[None]],
    ) -> None:
        if self._pubsub is None:
            raise BusConnectionError("Redis bus not started. Call start() first.")
        if topic not in self._handlers:
            self._handlers[topic] = []
            await self._pubsub.subscribe(topic)
        self._handlers[topic].append(handler)
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        while self._running and self._pubsub is not None:
            try:
                async for raw in self._pubsub.listen():
                    if not self._running:
                        break
                    if raw.get("type") == "message":
                        channel = raw.get("channel")
                        if isinstance(channel, bytes):
                            channel = channel.decode("utf-8")
                        data = raw.get("data")
                        if data is None:
                            continue
                        payload = data.decode("utf-8") if isinstance(data, bytes) else data
                        try:
                            msg = BusMessage.from_json(payload)
                            for h in self._handlers.get(channel, []):
                                await h(msg)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception:
                if self._running:
                    await asyncio.sleep(0.5)

    async def unsubscribe(self, topic: str) -> None:
        if self._pubsub is not None and topic in self._handlers:
            await self._pubsub.unsubscribe(topic)
        self._handlers.pop(topic, None)
