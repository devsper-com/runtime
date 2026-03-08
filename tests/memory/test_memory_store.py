"""Tests for memory storage and retrieval."""
import os
import tempfile

import pytest

from hivemind.memory.memory_store import MemoryStore, generate_memory_id
from hivemind.memory.memory_types import MemoryRecord, MemoryType


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = MemoryStore(db_path=path)
    yield s
    try:
        os.unlink(path)
    except Exception:
        pass


def test_store_and_retrieve(store):
    r = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.SEMANTIC,
        content="Test content",
        tags=["a", "b"],
        source_task="task_1",
    )
    mid = store.store(r)
    assert mid == r.id
    got = store.retrieve(mid)
    assert got is not None
    assert got.content == r.content
    assert got.tags == r.tags
    assert got.memory_type == r.memory_type


def test_retrieve_missing_returns_none(store):
    assert store.retrieve("nonexistent-id") is None


def test_delete(store):
    r = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.RESEARCH,
        content="To delete",
        tags=[],
    )
    store.store(r)
    assert store.retrieve(r.id) is not None
    ok = store.delete(r.id)
    assert ok is True
    assert store.retrieve(r.id) is None
    assert store.delete(r.id) is False


def test_list_memory(store):
    for i in range(5):
        store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content=f"Content {i}",
                tags=[],
            )
        )
    store.store(
        MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.RESEARCH,
            content="Research note",
            tags=[],
        )
    )
    all_records = store.list_memory(limit=10)
    assert len(all_records) == 6
    research_only = store.list_memory(memory_type=MemoryType.RESEARCH, limit=10)
    assert len(research_only) == 1
    assert research_only[0].memory_type == MemoryType.RESEARCH
