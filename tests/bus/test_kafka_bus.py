"""
Tests for KafkaBus backend.
All tests use mocks — no real Kafka broker required.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from devsper.bus.message import create_bus_message


@pytest.fixture
def mock_aiokafka(monkeypatch):
    """Patch aiokafka so KafkaBus can be imported without the package installed."""
    producer = AsyncMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock()

    consumer = AsyncMock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    consumer.commit = AsyncMock()
    consumer.subscription = MagicMock(return_value=set())
    consumer.subscribe = MagicMock()
    # __aiter__ returns empty iterator (no messages in unit tests)
    consumer.__aiter__ = MagicMock(return_value=iter([]))

    fake_aiokafka = MagicMock()
    fake_aiokafka.AIOKafkaProducer = MagicMock(return_value=producer)
    fake_aiokafka.AIOKafkaConsumer = MagicMock(return_value=consumer)

    monkeypatch.setitem(__import__("sys").modules, "aiokafka", fake_aiokafka)
    return {"producer": producer, "consumer": consumer, "module": fake_aiokafka}


def test_kafka_bus_import_error_without_aiokafka():
    """KafkaBus raises ImportError when aiokafka is not installed."""
    import sys
    with patch.dict(sys.modules, {"aiokafka": None}):
        with pytest.raises(ImportError, match="aiokafka"):
            from devsper.bus.backends.kafka import KafkaBus
            KafkaBus()


@pytest.mark.asyncio
async def test_kafka_bus_start_stop(mock_aiokafka):
    from devsper.bus.backends.kafka import KafkaBus
    bus = KafkaBus(bootstrap_servers=["localhost:9092"], group_id="test-group")
    await bus.start()
    assert bus._started is True
    await bus.stop()
    assert bus._started is False


@pytest.mark.asyncio
async def test_kafka_bus_publish(mock_aiokafka):
    from devsper.bus.backends.kafka import KafkaBus
    bus = KafkaBus(bootstrap_servers=["localhost:9092"])
    await bus.start()
    msg = create_bus_message(topic="task.assigned", payload={"key": "val"}, sender_id="s1", run_id="r1")
    await bus.publish(msg)
    mock_aiokafka["producer"].send_and_wait.assert_called_once()
    await bus.stop()


@pytest.mark.asyncio
async def test_kafka_bus_subscribe_registers_handler(mock_aiokafka):
    from devsper.bus.backends.kafka import KafkaBus
    bus = KafkaBus(bootstrap_servers=["localhost:9092"])
    await bus.start()
    received = []
    async def handler(msg):
        received.append(msg)
    await bus.subscribe("task.assigned", handler)
    assert "task.assigned" in bus._handlers
    await bus.stop()


@pytest.mark.asyncio
async def test_kafka_bus_unsubscribe_removes_handler(mock_aiokafka):
    from devsper.bus.backends.kafka import KafkaBus
    bus = KafkaBus(bootstrap_servers=["localhost:9092"])
    await bus.start()
    async def handler(msg):
        pass
    await bus.subscribe("task.assigned", handler)
    await bus.unsubscribe("task.assigned")
    assert "task.assigned" not in bus._handlers
    await bus.stop()


def test_kafka_bus_sanitize_topic():
    from devsper.bus.backends.kafka import _sanitize_topic
    assert _sanitize_topic("task.assigned") == "task_assigned"
    assert _sanitize_topic("result.*") == "result_all"


def test_get_bus_returns_kafka_bus(mock_aiokafka):
    from devsper.bus import get_bus

    cfg = MagicMock()
    cfg.bus.backend = "kafka"
    cfg.bus.kafka.bootstrap_servers = ["broker:9092"]
    cfg.bus.kafka.group_id = "my-group"
    cfg.bus.kafka.client_id = "my-client"

    from devsper.bus.backends.kafka import KafkaBus
    bus = get_bus(cfg)
    assert isinstance(bus, KafkaBus)


def test_get_bus_returns_in_memory_by_default():
    from devsper.bus import get_bus, InMemoryBus
    cfg = MagicMock()
    cfg.bus = None
    bus = get_bus(cfg)
    assert isinstance(bus, InMemoryBus)
