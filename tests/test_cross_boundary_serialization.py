"""Round-trip Task serialization across Python/Rust boundary (Python side)."""

import json
import pytest
from devsper.types.task import Task, TaskStatus


def _task_fixtures():
    """20 Task instances with varied field combinations."""
    return [
        Task(id="t1", description="d1", dependencies=[], status=TaskStatus.PENDING),
        Task(id="t2", description="d2", dependencies=["t1"], status=TaskStatus.COMPLETED, result="r2"),
        Task(id="t3", description="d3", dependencies=["t1", "t2"], status=TaskStatus.FAILED, error="e3"),
        Task(id="t4", description="d4", status=TaskStatus.RUNNING),
        Task(id="t5", description="", dependencies=[], result=None, error=None, speculative=True),
        Task(id="t6", description="d6", role="research", retry_count=2),
        Task(id="t7", description="d7", role="code", speculative=False, retry_count=0),
        Task(id="t8", description="d8", result="long result\nwith newlines"),
        Task(id="t9", description="d9", error="error with \"quotes\""),
        Task(id="t10", description="d10", dependencies=["a", "b", "c"], status=TaskStatus.COMPLETED),
        Task(id="t11", description="x" * 500),
        Task(id="t12", description="d12", role="critic", retry_count=3),
        Task(id="t13", description="d13", status=TaskStatus.PENDING, speculative=True),
        Task(id="t14", description="d14", result="", error=""),
        Task(id="t15", description="d15", dependencies=["single"]),
        Task(id="t16", description="d16", status=TaskStatus.COMPLETED, result="ok", role="analysis"),
        Task(id="t17", description="d17", status=TaskStatus.FAILED, error="fail", retry_count=1),
        Task(id="t18", description="d18", result=None),
        Task(id="t19", description="d19", role=None),
        Task(id="t20", description="d20", dependencies=[], status=TaskStatus.PENDING, retry_count=10),
    ]


@pytest.mark.parametrize("task", _task_fixtures(), ids=lambda t: t.id)
def test_task_roundtrip(task: Task) -> None:
    """Task.to_dict() -> JSON -> (Rust deser) -> JSON -> Task.from_dict() round-trip."""
    d = task.to_dict()
    raw = json.dumps(d)
    # Simulate Rust: deserialize then serialize again (Python as stand-in for Rust)
    d2 = json.loads(raw)
    raw2 = json.dumps(d2)
    restored = Task.from_dict(json.loads(raw2))
    assert restored.id == task.id
    assert restored.description == task.description
    assert restored.dependencies == task.dependencies
    assert restored.status == task.status
    assert restored.result == task.result
    assert restored.error == task.error
    assert restored.speculative == task.speculative
    assert restored.role == task.role
    assert restored.retry_count == task.retry_count
