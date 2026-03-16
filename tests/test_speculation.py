"""Tests for speculative execution."""

import pytest
from devsper.types.task import Task, TaskStatus
from devsper.swarm.scheduler import Scheduler
from devsper.swarm.speculation import (
    get_speculative_candidates,
    confirm_speculative,
    discard_speculative,
)


def test_speculative_candidates_one_dep_running():
    """When one dependency is RUNNING and rest COMPLETED, task is speculative candidate."""
    tasks = {
        "a": Task(id="a", description="A", dependencies=[], status=TaskStatus.RUNNING),
        "b": Task(
            id="b", description="B", dependencies=["a"], status=TaskStatus.PENDING
        ),
    }
    graph = type(
        "G", (), {"predecessors": lambda n: {"a": [], "b": ["a"]}.get(n, [])}
    )()

    # graph.predecessors must return iterable
    class G:
        def predecessors(self, n):
            return {"a": [], "b": ["a"]}.get(n, [])

    candidates = get_speculative_candidates(tasks, G())
    assert len(candidates) == 1
    assert candidates[0].id == "b"


def test_speculative_confirm_discard():
    """confirm_speculative keeps result; discard_speculative resets."""
    t = Task(id="x", description="X", dependencies=[], speculative=True, result="ok")
    confirm_speculative(t)
    assert t.status == TaskStatus.COMPLETED
    assert t.result == "ok"

    t2 = Task(id="y", description="Y", dependencies=[], speculative=True, result="ok")
    discard_speculative(t2)
    assert t2.status == TaskStatus.PENDING
    assert t2.result is None


def test_scheduler_get_speculative_tasks():
    """Scheduler returns speculative tasks when one dep is running."""
    tasks = [
        Task(id="1", description="First", dependencies=[]),
        Task(id="2", description="Second", dependencies=["1"]),
    ]
    s = Scheduler()
    s.add_tasks(tasks)
    s._tasks["1"].status = TaskStatus.RUNNING
    spec = s.get_speculative_tasks()
    assert len(spec) == 1
    assert spec[0].id == "2"
    assert spec[0].speculative is True
