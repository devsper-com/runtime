import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from unittest.mock import patch, MagicMock


def make_spec(with_mutation_point: bool = False) -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="researcher", role="Research the topic", is_mutation_point=with_mutation_point),
            NodeSpec(id="writer", role="Write the report"),
        ],
        edges=[EdgeSpec(src="researcher", dst="writer")],
    )


def test_compile_graph_returns_compiled_graph():
    """compile_graph should return an object with an invoke method (compiled StateGraph)."""
    from devsper.compiler.codegen import compile_graph

    # Patch the langgraph builder to avoid needing full runtime
    with patch("devsper.compiler.codegen._build_agent_node_fn", return_value=lambda s: s), \
         patch("devsper.compiler.codegen._build_mutation_node_fn", return_value=lambda s: s):
        compiled = compile_graph(make_spec())
        assert hasattr(compiled, "invoke") or hasattr(compiled, "ainvoke")


def test_compile_graph_entry_point_is_first_node_without_incoming_edges():
    from devsper.compiler.codegen import _find_entry
    spec = make_spec()
    entry = _find_entry(spec)
    assert entry == "researcher"  # "writer" has incoming edge from "researcher"


def test_find_entry_single_node():
    from devsper.compiler.codegen import _find_entry
    spec = GraphSpec(nodes=[NodeSpec(id="solo", role="Only node")], edges=[])
    assert _find_entry(spec) == "solo"
