import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.graph.runtime import GraphRuntime
from devsper.graph.state import initial_state


def two_node_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="researcher", role="Research the topic"),
            NodeSpec(id="writer", role="Write the report"),
        ],
        edges=[EdgeSpec(src="researcher", dst="writer")],
    )


def test_graph_runtime_compile_returns_compiled():
    rt = GraphRuntime()
    compiled = rt.compile(two_node_spec())
    assert hasattr(compiled, "invoke") or hasattr(compiled, "ainvoke")


def test_graph_runtime_run_returns_result():
    rt = GraphRuntime()
    result = rt.run_spec(two_node_spec(), task="research AI trends")
    assert result["task"] == "research AI trends"
    assert "researcher" in result["completed_nodes"]
    assert "writer" in result["completed_nodes"]


def test_graph_runtime_run_populates_results():
    rt = GraphRuntime()
    result = rt.run_spec(two_node_spec(), task="research AI")
    assert "researcher" in result["results"]
    assert "writer" in result["results"]


def test_graph_runtime_run_with_initial_state():
    rt = GraphRuntime()
    state = initial_state(task="custom task", run_id="test-run-001")
    result = rt.run_spec(two_node_spec(), state=state)
    assert result["run_id"] == "test-run-001"


def test_graph_runtime_mutation_checkpoint_spec():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="planner", role="Plan the work", is_mutation_point=True),
            NodeSpec(id="executor", role="Execute the plan"),
        ],
        edges=[EdgeSpec(src="planner", dst="executor")],
    )
    rt = GraphRuntime()
    result = rt.run_spec(spec, task="build a feature")
    assert "planner" in result["completed_nodes"]
    assert "executor" in result["completed_nodes"]
