"""
Kafka bus backend via aiokafka.
Gated behind the `distributed` extra — raises ImportError if aiokafka is not installed.

Consumer groups map to worker pools (each PeerNode = one consumer group).
Topics map 1:1 with BusTopics enum — no protocol change vs RedisBus.
Offsets committed after successful message processing (at-least-once delivery).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

from devsper.bus.message import BusMessage, create_bus_message
from devsper.bus.backends.base import BusBackend

logger = logging.getLogger(__name__)


class KafkaBus(BusBackend):
    """
    Kafka-backed message bus using aiokafka.

    Args:
        bootstrap_servers: Kafka broker addresses, e.g. ["localhost:9092"].
        group_id: Consumer group ID (each PeerNode should use a unique group_id).
        client_id: Optional client identifier for monitoring.
    """

    def __init__(
        self,
        bootstrap_servers: list[str] | str = "localhost:9092",
        group_id: str = "devsper-workers",
        client_id: str = "devsper-bus",
    ) -> None:
        try:
            import aiokafka  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "KafkaBus requires aiokafka. "
                "Install with: pip install 'devsper[distributed]' or pip install aiokafka"
            ) from exc

        if isinstance(bootstrap_servers, str):
            bootstrap_servers = [bootstrap_servers]
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._client_id = client_id

        self._producer: object | None = None
        self._consumer: object | None = None
        self._handlers: dict[str, list[Callable[[BusMessage], Awaitable[None]]]] = {}
        self._consumer_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._started = False

    async def start(self) -> None:
        """Connect producer and consumer to Kafka."""
        from aiokafka import AIOKafkaProducer, AIOKafkaConsumer  # type: ignore[import]

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            client_id=self._client_id,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()  # type: ignore[union-attr]

        self._consumer = AIOKafkaConsumer(
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            client_id=self._client_id,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await self._consumer.start()  # type: ignore[union-attr]

        self._started = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("KafkaBus started: brokers=%s group=%s", self._bootstrap_servers, self._group_id)

    async def stop(self) -> None:
        """Disconnect from Kafka cleanly."""
        self._started = False
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        if self._consumer is not None:
            await self._consumer.stop()  # type: ignore[union-attr]
        if self._producer is not None:
            await self._producer.stop()  # type: ignore[union-attr]
        self._handlers.clear()
        logger.info("KafkaBus stopped")

    async def publish(self, message: BusMessage) -> None:
        """Publish a BusMessage to the Kafka topic derived from message.topic."""
        if self._producer is None:
            raise RuntimeError("KafkaBus not started — call await bus.start() first")
        topic = _sanitize_topic(message.topic)
        payload = {
            "topic": message.topic,
            "payload": message.payload if isinstance(message.payload, dict) else vars(message.payload),
            "sender_id": message.sender_id,
            "run_id": message.run_id,
            "message_id": message.id,
            "timestamp": message.timestamp,
            "schema_version": getattr(message, "schema_version", "1.0"),
        }
        await self._producer.send_and_wait(topic, value=payload)  # type: ignore[union-attr]

    async def subscribe(
        self,
        topic: str,
        handler: Callable[[BusMessage], Awaitable[None]],
        run_id: str | None = None,
    ) -> None:
        """Register a handler for a topic. Subscribes the Kafka consumer if needed."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

        if self._consumer is not None:
            kafka_topic = _sanitize_topic(topic)
            current = set(self._consumer.subscription())  # type: ignore[union-attr]
            if kafka_topic not in current:
                self._consumer.subscribe(list(current | {kafka_topic}))  # type: ignore[union-attr]

    async def unsubscribe(self, topic: str) -> None:
        """Remove all handlers for a topic."""
        self._handlers.pop(topic, None)

    async def _consume_loop(self) -> None:
        """Background task: read from Kafka and dispatch to registered handlers."""
        if self._consumer is None:
            return
        try:
            async for record in self._consumer:  # type: ignore[union-attr]
                try:
                    raw = record.value
                    original_topic = raw.get("topic", record.topic)
                    msg = create_bus_message(
                        topic=original_topic,
                        payload=raw.get("payload", {}),
                        sender_id=raw.get("sender_id", ""),
                        run_id=raw.get("run_id", ""),
                    )
                    handlers = self._handlers.get(original_topic, [])
                    if handlers:
                        await asyncio.gather(*(h(msg) for h in handlers), return_exceptions=True)
                    # Commit offset after successful dispatch (at-least-once)
                    await self._consumer.commit()  # type: ignore[union-attr]
                except Exception:
                    logger.exception("KafkaBus: error processing record from topic %s", record.topic)
        except asyncio.CancelledError:
            pass


def _sanitize_topic(topic: str) -> str:
    """Convert bus topic (e.g. 'task.assigned') to valid Kafka topic name."""
    return topic.replace(".", "_").replace("*", "all")
