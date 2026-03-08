"""Tests for memory summarizer, namespaces, scoring."""

from datetime import datetime, timezone, timedelta

from hivemind.memory.memory_types import MemoryRecord, MemoryType
from hivemind.memory.summarizer import summarize_extractive, summarize
from hivemind.memory.namespaces import (
    add_namespace,
    record_namespace,
    filter_by_namespace,
    RESEARCH_MEMORY,
    namespace_tag,
)
from hivemind.memory.scoring import recency_score, score_and_sort


def test_summarize_extractive_empty():
    assert summarize_extractive([]) == ""


def test_summarize_extractive():
    r = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="First content.")
    r2 = MemoryRecord(id="2", memory_type=MemoryType.RESEARCH, content="Second content.")
    out = summarize_extractive([r, r2], max_chars=50)
    assert "First" in out or "Second" in out


def test_summarize_no_llm():
    r = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="Content here.")
    assert "Content" in summarize([r], use_llm=False)


def test_namespace_tag():
    assert namespace_tag("research_memory") == "ns:research_memory"


def test_add_namespace():
    r = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="x", tags=[])
    r2 = add_namespace(r, RESEARCH_MEMORY)
    assert namespace_tag(RESEARCH_MEMORY) in r2.tags


def test_record_namespace():
    r = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="x", tags=["ns:research_memory"])
    assert record_namespace(r) == "research_memory"


def test_filter_by_namespace():
    r1 = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="x", tags=["ns:research_memory"])
    r2 = MemoryRecord(id="2", memory_type=MemoryType.RESEARCH, content="y", tags=["ns:coding_memory"])
    filtered = filter_by_namespace([r1, r2], "research_memory")
    assert len(filtered) == 1 and filtered[0].id == "1"


def test_recency_score_newer_higher():
    now = datetime.now(timezone.utc)
    r_old = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="x", timestamp=now - timedelta(days=2))
    r_new = MemoryRecord(id="2", memory_type=MemoryType.RESEARCH, content="y", timestamp=now)
    assert recency_score(r_new, now) > recency_score(r_old, now)


def test_score_and_sort_returns_sorted():
    r = MemoryRecord(id="1", memory_type=MemoryType.RESEARCH, content="short")
    r2 = MemoryRecord(id="2", memory_type=MemoryType.RESEARCH, content="x" * 1000)
    scored = score_and_sort([r, r2], similarity_scores=[0.5, 0.5])
    assert len(scored) == 2
    assert scored[0][1] >= scored[1][1]
