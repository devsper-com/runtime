from __future__ import annotations
import dataclasses as _dc
from dataclasses import dataclass, field
from typing import Literal
import json
import hashlib


@dataclass
class RawWorkflowDoc:
    """Intermediate parse result before GraphSpec construction."""
    title: str = ""
    description: str = ""
    agents: list[dict] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class NodeSpec:
    id: str
    role: str
    tools: list[str] = field(default_factory=list)
    model_hint: Literal["fast", "mid", "slow"] | str = "mid"
    is_mutation_point: bool = False


@dataclass
class EdgeSpec:
    src: str
    dst: str
    condition: str | None = None


# Module-level field sets for forward-compat filtering in from_dict (avoids recomputing per call)
_node_fields: set[str] = {f.name for f in _dc.fields(NodeSpec)}
_edge_fields: set[str] = {f.name for f in _dc.fields(EdgeSpec)}


@dataclass
class GraphSpec:
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    mutation_points: list[str] = field(default_factory=list)
    state_schema: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    version: str = ""

    def __post_init__(self) -> None:
        # mutation_points is always derived from node.is_mutation_point — any caller-supplied value is overwritten
        self.mutation_points = [n.id for n in self.nodes if n.is_mutation_point]
        if not self.version:
            payload = json.dumps(
                {
                    "nodes": sorted(n.id for n in self.nodes),
                    "edges": sorted((e.src, e.dst) for e in self.edges),
                },
                sort_keys=True,
            )
            self.version = hashlib.sha256(payload.encode()).hexdigest()[:8]

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "role": n.role,
                    "tools": n.tools,
                    "model_hint": n.model_hint,
                    "is_mutation_point": n.is_mutation_point,
                }
                for n in self.nodes
            ],
            "edges": [{"src": e.src, "dst": e.dst, "condition": e.condition} for e in self.edges],
            "mutation_points": self.mutation_points,  # derivative of node flags; not read by from_dict
            "state_schema": self.state_schema,
            "metadata": self.metadata,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphSpec":
        nodes = [NodeSpec(**{k: v for k, v in n.items() if k in _node_fields}) for n in data["nodes"]]
        edges = [EdgeSpec(**{k: v for k, v in e.items() if k in _edge_fields}) for e in data["edges"]]
        spec = cls(
            nodes=nodes,
            edges=edges,
            state_schema=data.get("state_schema", {}),
            metadata=data.get("metadata", {}),
        )
        spec.version = data.get("version", spec.version)
        return spec
