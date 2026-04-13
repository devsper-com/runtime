import pytest
from devsper.compiler.ir import NodeSpec, EdgeSpec, GraphSpec


def test_node_spec_defaults():
    node = NodeSpec(id="n1", role="Research agent")
    assert node.tools == []
    assert node.model_hint == "mid"
    assert node.is_mutation_point is False


def test_edge_spec_defaults():
    edge = EdgeSpec(src="n1", dst="n2")
    assert edge.condition is None


def test_graph_spec_auto_version():
    spec = GraphSpec(
        nodes=[NodeSpec(id="n1", role="researcher")],
        edges=[],
    )
    assert len(spec.version) == 8


def test_graph_spec_mutation_points_auto_populated():
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="n1", role="researcher", is_mutation_point=True),
            NodeSpec(id="n2", role="writer"),
        ],
        edges=[EdgeSpec(src="n1", dst="n2")],
    )
    assert spec.mutation_points == ["n1"]


def test_graph_spec_round_trip():
    spec = GraphSpec(
        nodes=[NodeSpec(id="n1", role="researcher", tools=["web_search"], is_mutation_point=True)],
        edges=[EdgeSpec(src="n1", dst="END")],
        state_schema={"task": "str"},
    )
    data = spec.to_dict()
    restored = GraphSpec.from_dict(data)
    assert restored.nodes[0].id == "n1"
    assert restored.nodes[0].tools == ["web_search"]
    assert restored.nodes[0].is_mutation_point is True
    assert restored.edges[0].src == "n1"
    assert restored.version == spec.version


def test_graph_spec_two_identical_specs_same_version():
    def make():
        return GraphSpec(
            nodes=[NodeSpec(id="n1", role="researcher")],
            edges=[],
        )
    assert make().version == make().version


def test_graph_spec_version_order_independent():
    """Same nodes/edges in different insertion order must produce the same version."""
    spec_a = GraphSpec(
        nodes=[NodeSpec(id="n1", role="a"), NodeSpec(id="n2", role="b")],
        edges=[EdgeSpec(src="n1", dst="n2")],
    )
    spec_b = GraphSpec(
        nodes=[NodeSpec(id="n2", role="b"), NodeSpec(id="n1", role="a")],
        edges=[EdgeSpec(src="n1", dst="n2")],
    )
    assert spec_a.version == spec_b.version
