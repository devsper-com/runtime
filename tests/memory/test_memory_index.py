"""Tests for memory index (embedding search)."""
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from devsper.memory.memory_store import MemoryStore, generate_memory_id
from devsper.memory.memory_index import MemoryIndex
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.memory.embeddings import embed_text
from devsper.memory.supermemory_rust_ranker import format_memory_context


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


def test_query_memory_supermemory_lexical_fallback():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        s = MemoryStore(db_path=path)
        # Intentionally store records without embeddings to exercise lexical fallback.
        for content in [
            "code refactoring and linting",
            "dataset statistics and metrics",
        ]:
            mt = (
                MemoryType.ARTIFACT
                if "code" in content.lower()
                else MemoryType.SEMANTIC
            )
            r = MemoryRecord(
                id=generate_memory_id(),
                memory_type=mt,
                content=content,
                tags=[],
                embedding=None,
            )
            s.store(r)

        index = MemoryIndex(s, ranking_backend="supermemory")
        results = index.query_memory(
            "code refactoring",
            top_k=2,
            min_similarity=0.1,
            namespace=None,
        )
        assert results
        assert "code" in results[0].content.lower()
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_query_memory_supermemory_top_k(store_with_records):
    index = MemoryIndex(store_with_records, ranking_backend="supermemory")
    results = index.query_memory(
        "diffusion models for image generation",
        top_k=1,
        min_similarity=0.0,
        namespace=None,
    )
    assert len(results) <= 1
    if results:
        assert "diffusion" in results[0].content.lower() or "image" in results[0].content.lower()


def test_query_memory_supermemory_dedup_prefers_newer():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        s = MemoryStore(db_path=path)
        now = datetime.now(timezone.utc)
        older = now - timedelta(hours=1)

        q = "code refactoring and linting"
        content1 = "code refactoring and linting"
        content2 = "code refactoring and linting!!!"  # same token signature

        r1 = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.ARTIFACT,
            content=content1,
            tags=[],
            embedding=None,
            timestamp=older,
        )
        r2 = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.ARTIFACT,
            content=content2,
            tags=[],
            embedding=None,
            timestamp=now,
        )
        s.store(r1)
        s.store(r2)

        index = MemoryIndex(s, ranking_backend="supermemory")
        results = index.query_memory(q, top_k=5, min_similarity=0.0, namespace=None)
        assert len(results) == 1
        assert results[0].id == r2.id
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_query_memory_supermemory_recency_tiebreak():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        s = MemoryStore(db_path=path)
        now = datetime.now(timezone.utc)
        older = now - timedelta(hours=1)

        q = "code refactoring"
        content = "code refactoring and linting"

        r_old = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.ARTIFACT,
            content=content,
            tags=[],
            embedding=None,
            timestamp=older,
        )
        r_new = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.ARTIFACT,
            content=content + " extra",  # avoid dedup collision; lexical overlap stays equal
            tags=[],
            embedding=None,
            timestamp=now,
        )
        s.store(r_old)
        s.store(r_new)

        index = MemoryIndex(s, ranking_backend="supermemory")
        results = index.query_memory(q, top_k=2, min_similarity=0.0, namespace=None)
        assert results
        # Scores should tie; recency should win.
        assert results[0].id == r_new.id
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_query_memory_supermemory_memorytype_weighting():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        s = MemoryStore(db_path=path)
        now = datetime.now(timezone.utc)

        q = "code refactoring and linting"
        research_content = "code refactoring and linting"
        episodic_content = "code refactoring and linting extra"

        r_research = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.RESEARCH,
            content=research_content,
            tags=[],
            embedding=None,
            timestamp=now,
        )
        r_episodic = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.EPISODIC,
            content=episodic_content,
            tags=[],
            embedding=None,
            timestamp=now,
        )
        s.store(r_research)
        s.store(r_episodic)

        index = MemoryIndex(s, ranking_backend="supermemory")
        results = index.query_memory(q, top_k=2, min_similarity=0.0, namespace=None)
        assert results
        assert results[0].id == r_research.id
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_memory_context_formatting_skip_user_injection_from_ranked():
    now = datetime.now(timezone.utc)
    user_inj = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.EPISODIC,
        source_task="user_injection",
        content="Remember: I like pineapple on pizza.",
        tags=["user_injection"],
        embedding=None,
        timestamp=now,
    )

    ranked_duplicate = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.ARTIFACT,
        source_task="",
        content="Remember: I like pineapple on pizza.",
        tags=["user_injection"],
        embedding=None,
        timestamp=now,
    )
    ranked_real = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.SEMANTIC,
        source_task="task-1",
        content="Project uses Rust for local ranking logic.",
        tags=[],
        embedding=None,
        timestamp=now,
    )

    ctx = format_memory_context(
        user_injections=[user_inj],
        ranked_candidates=[ranked_duplicate, ranked_real],
    )
    assert "USER INJECTIONS" in ctx
    assert "RELEVANT MEMORY" in ctx
    # Duplicate should not appear under relevant memories.
    assert "pineapple on pizza" in ctx
    assert "- [artifact]" not in ctx

