"""Tests for learning engine."""
import os
import tempfile
from pathlib import Path

import pytest

from devsper.intelligence.learning_engine import LearningEngine
from devsper.memory.memory_store import MemoryStore, get_default_store, generate_memory_id
from devsper.memory.memory_types import MemoryRecord, MemoryType


@pytest.fixture
def events_dir():
    d = tempfile.mkdtemp()
    yield d
    import shutil
    try:
        shutil.rmtree(d)
    except Exception:
        pass


def test_analyze_telemetry_empty(events_dir):
    engine = LearningEngine(events_folder=events_dir)
    tele = engine.analyze_telemetry()
    assert tele["tasks_completed"] == 0
    assert "task_success_rate" in tele


def test_get_failure_patterns_empty(events_dir):
    engine = LearningEngine(events_folder=events_dir)
    patterns = engine.get_failure_patterns()
    assert isinstance(patterns, list)


def test_summarize_memory_for_learning():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=path)
    store.store(
        MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.RESEARCH,
            content="Some finding",
            tags=[],
        )
    )
    engine = LearningEngine(memory_store=store)
    summary = engine.summarize_memory_for_learning(limit=10)
    assert isinstance(summary, dict)
    try:
        os.unlink(path)
    except Exception:
        pass
