import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.graph.mutations import MutationRequest, MutationValidator


def base_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="n0", role="Researcher"),
            NodeSpec(id="n1", role="Writer"),
        ],
        edges=[EdgeSpec(src="n0", dst="n1")],
    )


def test_mutation_request_dataclass():
    req = MutationRequest(
        op="add_node",
        payload={"id": "n2", "role": "Editor"},
        justification="Need an editing pass",
        confidence=0.85,
    )
    assert req.op == "add_node"
    assert req.confidence == 0.85


def test_validator_rejects_low_confidence():
    validator = MutationValidator(confidence_threshold=0.7)
    req = MutationRequest(op="add_node", payload={"id": "n2", "role": "Editor"}, justification="x", confidence=0.5)
    assert not validator.validate(req, base_spec())


def test_validator_accepts_add_node():
    validator = MutationValidator()
    req = MutationRequest(op="add_node", payload={"id": "n2", "role": "Editor"}, justification="need editor", confidence=0.9)
    assert validator.validate(req, base_spec())


def test_validator_rejects_duplicate_node_id():
    validator = MutationValidator()
    req = MutationRequest(op="add_node", payload={"id": "n0", "role": "Duplicate"}, justification="dup", confidence=0.9)
    assert not validator.validate(req, base_spec())


def test_apply_add_node_extends_spec():
    validator = MutationValidator()
    req = MutationRequest(op="add_node", payload={"id": "n2", "role": "Editor"}, justification="edit", confidence=0.9)
    new_spec = validator.apply(req, base_spec())
    assert len(new_spec.nodes) == 3
    assert any(n.id == "n2" for n in new_spec.nodes)


def test_apply_remove_node_shrinks_spec():
    validator = MutationValidator()
    req = MutationRequest(op="remove_node", payload={"id": "n1"}, justification="not needed", confidence=0.9)
    new_spec = validator.apply(req, base_spec())
    assert len(new_spec.nodes) == 1
    assert all(n.id != "n1" for n in new_spec.nodes)


def test_validator_rejects_remove_last_node():
    validator = MutationValidator()
    single = GraphSpec(nodes=[NodeSpec(id="only", role="Solo")], edges=[])
    req = MutationRequest(op="remove_node", payload={"id": "only"}, justification="x", confidence=0.9)
    assert not validator.validate(req, single)


def test_mutation_request_to_dict_round_trip():
    req = MutationRequest(op="add_node", payload={"id": "n2", "role": "x"}, justification="y", confidence=0.8)
    data = req.to_dict()
    restored = MutationRequest.from_dict(data)
    assert restored.op == req.op
    assert restored.confidence == req.confidence
