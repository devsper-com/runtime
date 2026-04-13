from devsper.graph.state import AgentState, initial_state


def test_agent_state_is_typed_dict():
    state: AgentState = initial_state(task="research AI trends", run_id="run-001")
    assert state["task"] == "research AI trends"
    assert state["run_id"] == "run-001"
    assert state["messages"] == []
    assert state["results"] == {}
    assert state["pending_mutations"] == []
    assert state["graph_spec"] == {}
    assert state["budget_used"] == 0.0
    assert state["completed_nodes"] == []


def test_initial_state_defaults():
    state = initial_state(task="test")
    assert "run_id" in state
    assert len(state["run_id"]) > 0  # auto-generated if not provided


def test_agent_state_results_update():
    state = initial_state(task="test", run_id="r1")
    updated = {**state, "results": {**state["results"], "node_a": "output text"}}
    assert updated["results"]["node_a"] == "output text"


def test_agent_state_completed_nodes_append():
    state = initial_state(task="test", run_id="r1")
    updated = {**state, "completed_nodes": state["completed_nodes"] + ["node_a"]}
    assert "node_a" in updated["completed_nodes"]
