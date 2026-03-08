"""Tests for task result cache."""

import tempfile
import pytest
from pathlib import Path
from hivemind.types.task import Task
from hivemind.cache.hashing import task_hash
from hivemind.cache.task_cache import TaskCache


def test_task_hash_stable():
    """Same inputs produce same hash."""
    h1 = task_hash("id1", "desc", ["a", "b"])
    h2 = task_hash("id1", "desc", ["a", "b"])
    assert h1 == h2
    h3 = task_hash("id1", "desc", ["b", "a"])
    assert h1 == h3  # sorted deps


def test_task_cache_get_set():
    """Cache get/set roundtrip."""
    with tempfile.TemporaryDirectory() as d:
        cache = TaskCache(db_path=Path(d) / "cache.db")
        t = Task(id="t1", description="Do something", dependencies=[])
        assert cache.get(t) is None
        cache.set(t, "result text")
        assert cache.get(t) == "result text"


def test_task_cache_clear():
    """Clear removes all entries."""
    with tempfile.TemporaryDirectory() as d:
        cache = TaskCache(db_path=Path(d) / "cache.db")
        t = Task(id="t1", description="Do something", dependencies=[])
        cache.set(t, "r")
        assert cache.stats()["entries"] == 1
        cache.clear()
        assert cache.stats()["entries"] == 0
        assert cache.get(t) is None
