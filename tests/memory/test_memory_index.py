"""Tests for memory index (embedding search)."""
import os
import tempfile

import pytest

from devsper.memory.memory_store import MemoryStore, generate_memory_id
from devsper.memory.memory_index import MemoryIndex
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.memory.embeddings import embed_text


def test_embed_text_returns_list():
    emb = embed_text("hello world")
    assert isinstance(emb, list)
    assert len(emb) > 0
    assert all(isinstance(x, float) for x in emb)


def test_embed_text_deterministic():
    a = embed_text("same text")
    b = embed_text("same text")
    assert a == b


@pytest.fixture
def store_with_records():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = MemoryStore(db_path=path)
    index = MemoryIndex(s)
    for content in [
        "diffusion models for image generation",
        "code refactoring and linting",
        "dataset statistics and metrics",
    ]:
        mt = MemoryType.RESEARCH if "diffusion" in content else (MemoryType.ARTIFACT if "code" in content else MemoryType.SEMANTIC)
        r = MemoryRecord(id=generate_memory_id(), memory_type=mt, content=content, tags=[])
        r = index.ensure_embedding(r)
        s.store(r)
    try:
        yield s
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_query_memory_top_k(store_with_records):
    index = MemoryIndex(store_with_records)
    results = index.query_memory("diffusion and image generation", top_k=2)
    assert len(results) <= 2
    assert len(results) >= 1
    if results:
        assert "diffusion" in results[0].content.lower() or "image" in results[0].content.lower()


def test_query_memory_empty_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = MemoryStore(db_path=path)
    index = MemoryIndex(s)
    assert index.query_memory("anything", top_k=5) == []
    try:
        os.unlink(path)
    except Exception:
        pass
