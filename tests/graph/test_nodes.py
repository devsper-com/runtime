from devsper.compiler.ir import NodeSpec
from devsper.graph.nodes import build_agent_node, build_mutation_checkpoint_node
from devsper.graph.state import initial_state


def test_build_agent_node_returns_callable():
    node = NodeSpec(id="n1", role="Researcher")
    fn = build_agent_node(node)
    assert callable(fn)


def test_agent_node_returns_state_update():
    node = NodeSpec(id="n1", role="Researcher")
    fn = build_agent_node(node)
    state = initial_state(task="research AI", run_id="r1")
    result = fn(state)
    assert isinstance(result, dict)
    assert "n1" in result.get("completed_nodes", [])


def test_build_mutation_checkpoint_node_returns_callable():
    node = NodeSpec(id="m1", role="Planner", is_mutation_point=True)
    fn = build_mutation_checkpoint_node(node)
    assert callable(fn)


def test_mutation_checkpoint_node_returns_state_update():
    node = NodeSpec(id="m1", role="Planner", is_mutation_point=True)
    fn = build_mutation_checkpoint_node(node)
    state = initial_state(task="plan research", run_id="r1")
    result = fn(state)
    assert isinstance(result, dict)
    assert "m1" in result.get("completed_nodes", [])


def test_agent_node_records_result():
    node = NodeSpec(id="researcher", role="Research agent")
    fn = build_agent_node(node)
    state = initial_state(task="research quantum", run_id="r1")
    result = fn(state)
    assert "researcher" in result.get("results", {})
