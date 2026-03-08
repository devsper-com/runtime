"""Tests for memory router (relevant memory for task)."""
import os
import tempfile

import pytest

from hivemind.memory.memory_store import MemoryStore, generate_memory_id
from hivemind.memory.memory_index import MemoryIndex
from hivemind.memory.memory_router import MemoryRouter
from hivemind.memory.memory_types import MemoryRecord, MemoryType


@pytest.fixture
def router():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=path)
    index = MemoryIndex(store)
    r = MemoryRouter(store=store, index=index, top_k=3)
    yield r
    try:
        os.unlink(path)
    except Exception:
        pass


def test_get_memory_context_empty(router):
    ctx = router.get_memory_context("analyze papers")
    assert ctx == "" or "RELEVANT" in ctx or "memory" in ctx.lower()


def test_get_memory_context_with_memory(router):
    store = router.store
    index = router.index
    r = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.RESEARCH,
        content="Previous finding: diffusion models improve with more steps.",
        tags=["research"],
    )
    r = index.ensure_embedding(r)
    store.store(r)
    ctx = router.get_memory_context("analyze diffusion model papers")
    assert "diffusion" in ctx or "Previous" in ctx or "RELEVANT" in ctx
