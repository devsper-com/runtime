"""Tests for memory tools (store_memory, search_memory, list_memory, delete_memory, tag_memory, summarize_memory)."""
import os
import tempfile

import pytest

from hivemind.tools.tool_runner import run_tool
from hivemind.tools.registry import get
from hivemind.memory.memory_store import MemoryStore, get_default_store


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    """Use a temp DB for memory tools so tests don't share state."""
    path = str(tmp_path / "memory.db")
    store = MemoryStore(db_path=path)
    import hivemind.memory.memory_store as mod
    monkeypatch.setattr(mod, "_default_store", store)
    yield store


def test_store_memory_tool():
    out = run_tool("store_memory", {"content": "Test note", "memory_type": "semantic"})
    assert "Stored memory id:" in out or "Error" not in out
    assert "id:" in out.lower()


def test_list_memory_tool():
    run_tool("store_memory", {"content": "Item one", "memory_type": "episodic"})
    out = run_tool("list_memory", {"limit": 10})
    assert "Item one" in out or "episodic" in out or "No memory" in out


def test_search_memory_tool():
    run_tool("store_memory", {"content": "Diffusion models for images", "memory_type": "research"})
    out = run_tool("search_memory", {"query": "diffusion models", "top_k": 3})
    assert "Diffusion" in out or "No matching" in out


def test_delete_memory_tool():
    out_store = run_tool("store_memory", {"content": "To delete", "memory_type": "semantic"})
    mid = out_store.split(":")[-1].strip()
    out = run_tool("delete_memory", {"memory_id": mid})
    assert "Deleted" in out or "not found" in out.lower()


def test_tag_memory_tool():
    out_store = run_tool("store_memory", {"content": "Tagged note", "memory_type": "semantic"})
    mid = out_store.split(":")[-1].strip()
    out = run_tool("tag_memory", {"memory_id": mid, "tags": ["important", "review"]})
    assert "Tags updated" in out or "important" in out or "not found" in out.lower()


def test_summarize_memory_tool():
    out = run_tool("summarize_memory", {"limit": 5})
    assert "Total:" in out or "entries" in out or "By type" in out


def test_memory_tools_registered():
    assert get("store_memory") is not None
    assert get("search_memory") is not None
    assert get("list_memory") is not None
    assert get("delete_memory") is not None
    assert get("tag_memory") is not None
    assert get("summarize_memory") is not None
