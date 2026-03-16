"""Node metadata and cluster state for distributed execution."""

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any


class NodeRole(Enum):
    CONTROLLER = "controller"
    WORKER = "worker"
    HYBRID = "hybrid"


@dataclass
class NodeInfo:
    """Serializable node registration info."""
    node_id: str
    role: NodeRole
    host: str
    rpc_port: int
    rpc_url: str
    tags: list[str]
    max_workers: int
    joined_at: str
    last_heartbeat: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role.value,
            "host": self.host,
            "rpc_port": self.rpc_port,
            "rpc_url": self.rpc_url,
            "tags": list(self.tags),
            "max_workers": self.max_workers,
            "joined_at": self.joined_at,
            "last_heartbeat": self.last_heartbeat,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeInfo":
        role_val = data.get("role", "worker")
        if isinstance(role_val, NodeRole):
            role = role_val
        else:
            role = NodeRole(role_val) if role_val in ("controller", "worker", "hybrid") else NodeRole.WORKER
        return cls(
            node_id=data["node_id"],
            role=role,
            host=data.get("host", ""),
            rpc_port=int(data.get("rpc_port", 0)),
            rpc_url=data.get("rpc_url", ""),
            tags=list(data.get("tags", [])),
            max_workers=int(data.get("max_workers", 1)),
            joined_at=data.get("joined_at", ""),
            last_heartbeat=data.get("last_heartbeat", ""),
            version=data.get("version", ""),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "NodeInfo":
        return cls.from_dict(json.loads(raw))


@dataclass
class ClusterState:
    """Current view of the cluster."""
    nodes: dict[str, NodeInfo] = field(default_factory=dict)
    controller_id: str | None = None
    run_id: str | None = None
    quorum: bool = False
