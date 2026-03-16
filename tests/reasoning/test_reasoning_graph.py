"""Tests for reasoning graph: nodes, graph, store."""

from datetime import datetime, timezone

import pytest

from devsper.reasoning.nodes import ReasoningNode
from devsper.reasoning.graph import ReasoningGraph
from devsper.reasoning.store import ReasoningStore


def test_reasoning_node_has_required_fields():
    n = ReasoningNode(
        id="n1",
        agent_id="a1",
        task_id="t1",
        content="Conclusion: X.",
        dependencies=["n0"],
    )
    assert n.id == "n1"
    assert n.agent_id == "a1"
    assert n.task_id == "t1"
    assert n.content == "Conclusion: X."
    assert n.dependencies == ["n0"]
    assert isinstance(n.timestamp, datetime)


def test_reasoning_graph_add_node_and_query():
    g = ReasoningGraph()
    n1 = ReasoningNode(id="n1", agent_id="a1", task_id="t1", content="Step 1", dependencies=[])
    n2 = ReasoningNode(id="n2", agent_id="a1", task_id="t2", content="Step 2", dependencies=["n1"])
    g.add_node(n1)
    g.add_node(n2)

    by_task = g.query_nodes(task_id="t1")
    assert len(by_task) == 1
    assert by_task[0].id == "n1"

    by_agent = g.query_nodes(agent_id="a1")
    assert len(by_agent) == 2

    deps = g.get_dependencies("n2")
    assert len(deps) == 1
    assert deps[0].id == "n1"


def test_reasoning_store_add_and_query():
    store = ReasoningStore()
    node1 = store.add_node(agent_id="ag1", task_id="task_1", content="Reasoning step one")
    assert node1.id is not None
    assert node1.agent_id == "ag1"
    assert node1.task_id == "task_1"

    store.add_node(agent_id="ag1", task_id="task_1", content="Step two", dependencies=[node1.id])
    nodes = store.query_nodes(task_id="task_1")
    assert len(nodes) >= 2
    deps = store.get_dependencies(nodes[0].id)
    assert isinstance(deps, list)
