"""Execution graph description / agent_name guarantees."""

from devsper.runtime.execution_graph import ExecutionGraph
from devsper.types.task import Task


def test_empty_description_uses_role():
    g = ExecutionGraph()
    t = Task(id="t1", description="", role="research", dependencies=[])
    g.add_task(t)
    d = g.to_dict()["t1"]
    assert "research" in d["description"].lower()
    assert d["agent_name"] == "research"


def test_empty_description_uses_agent_field():
    g = ExecutionGraph()
    t = Task(id="t1", description="", role=None, dependencies=[], agent="coder")
    g.add_task(t)
    d = g.to_dict()["t1"]
    assert "coder" in d["description"].lower()
    assert d["agent_name"] == "coder"


def test_assign_worker_stub_has_no_raw_id_only_label():
    g = ExecutionGraph()
    g.assign_worker("unknown-id", "worker-1")
    d = g.to_dict()["unknown-id"]
    assert d["description"]
    assert d["agent_name"]
    assert "unknown-id" != d["description"]
