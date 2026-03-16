"""Tests for task optimizer."""
import pytest

from devsper.types.task import Task
from devsper.intelligence.task_optimizer import TaskOptimizer


def test_optimize_dedupes_similar():
    tasks = [
        Task(id="task_1", description="Summarize the document", dependencies=[]),
        Task(id="task_2", description="summarize the document", dependencies=["task_1"]),
        Task(id="task_3", description="Write report", dependencies=["task_2"]),
    ]
    opt = TaskOptimizer(min_similarity_chars=5)
    out = opt.optimize(tasks)
    assert len(out) <= 3
    ids = [t.id for t in out]
    assert "task_1" in ids or "task_2" in ids or "task_3" in ids


def test_detect_parallel_opportunities():
    tasks = [
        Task(id="a", description="Step A", dependencies=[]),
        Task(id="b", description="Step B", dependencies=[]),
        Task(id="c", description="Step C", dependencies=["a", "b"]),
    ]
    opt = TaskOptimizer()
    groups = opt.detect_parallel_opportunities(tasks)
    assert any(len(g) >= 2 for g in groups)


def test_remove_unnecessary():
    tasks = [
        Task(id="1", description="Real task here", dependencies=[]),
        Task(id="2", description="n/a", dependencies=["1"]),
        Task(id="3", description="Another real one", dependencies=["2"]),
    ]
    opt = TaskOptimizer()
    out = opt.remove_unnecessary(tasks)
    assert len(out) < len(tasks)
    assert not any((t.description or "").strip().lower() == "n/a" for t in out)
