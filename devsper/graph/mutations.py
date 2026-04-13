from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Literal
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec


@dataclass
class MutationRequest:
    op: Literal["add_node", "remove_node", "add_edge", "fork_subgraph"]
    payload: dict
    justification: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "payload": self.payload,
            "justification": self.justification,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MutationRequest":
        return cls(
            op=data["op"],
            payload=data["payload"],
            justification=data["justification"],
            confidence=data["confidence"],
        )


class MutationValidator:
    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self.confidence_threshold = confidence_threshold

    def validate(self, req: MutationRequest, spec: GraphSpec) -> bool:
        """Return True if mutation is safe to apply."""
        if req.confidence < self.confidence_threshold:
            return False
        if req.op == "add_node":
            new_id = req.payload.get("id", "")
            existing = {n.id for n in spec.nodes}
            return bool(new_id) and new_id not in existing
        if req.op == "remove_node":
            if len(spec.nodes) <= 1:
                return False
            target = req.payload.get("id", "")
            return any(n.id == target for n in spec.nodes)
        if req.op == "add_edge":
            src = req.payload.get("src", "")
            dst = req.payload.get("dst", "")
            existing_ids = {n.id for n in spec.nodes}
            return src in existing_ids and dst in existing_ids
        return False

    def apply(self, req: MutationRequest, spec: GraphSpec) -> GraphSpec:
        """Apply a validated mutation. Returns a new GraphSpec."""
        new_spec = copy.deepcopy(spec)
        if req.op == "add_node":
            new_node = NodeSpec(
                id=req.payload["id"],
                role=req.payload.get("role", "New agent"),
                tools=req.payload.get("tools", []),
                model_hint=req.payload.get("model_hint", "mid"),
                is_mutation_point=req.payload.get("is_mutation_point", False),
            )
            new_spec.nodes.append(new_node)
            # Wire new node after the last existing node
            if len(new_spec.nodes) >= 2:
                prev = new_spec.nodes[-2]
                new_spec.edges.append(EdgeSpec(src=prev.id, dst=new_node.id))
        elif req.op == "remove_node":
            target_id = req.payload["id"]
            new_spec.nodes = [n for n in new_spec.nodes if n.id != target_id]
            new_spec.edges = [
                e for e in new_spec.edges
                if e.src != target_id and e.dst != target_id
            ]
        elif req.op == "add_edge":
            new_spec.edges.append(EdgeSpec(
                src=req.payload["src"],
                dst=req.payload["dst"],
                condition=req.payload.get("condition"),
            ))
        new_spec.mutation_points = [n.id for n in new_spec.nodes if n.is_mutation_point]
        return new_spec
