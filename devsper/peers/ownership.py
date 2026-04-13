"""
SubgraphOwnership: tracks which PeerNode leads which subgraph.
Leadership is per-subgraph — any node can lead any subgraph.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SubgraphOwnership:
    """Thread-safe registry mapping subgraph_id → leader_node_id."""
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _owners: dict[str, str] = field(default_factory=dict, init=False)

    def claim(self, subgraph_id: str, node_id: str) -> bool:
        """
        Attempt to claim leadership for a subgraph.
        Returns True if claim succeeds (no existing leader or same node reclaims).
        """
        with self._lock:
            existing = self._owners.get(subgraph_id)
            if existing is None or existing == node_id:
                self._owners[subgraph_id] = node_id
                return True
            return False

    def release(self, subgraph_id: str, node_id: str) -> bool:
        """Release leadership. Only the current leader can release."""
        with self._lock:
            if self._owners.get(subgraph_id) == node_id:
                del self._owners[subgraph_id]
                return True
            return False

    def transfer(self, subgraph_id: str, from_node: str, to_node: str) -> bool:
        """Transfer leadership from one node to another."""
        with self._lock:
            if self._owners.get(subgraph_id) == from_node:
                self._owners[subgraph_id] = to_node
                return True
            return False

    def leader_of(self, subgraph_id: str) -> str | None:
        """Return the current leader for a subgraph, or None."""
        with self._lock:
            return self._owners.get(subgraph_id)

    def owned_by(self, node_id: str) -> set[str]:
        """Return all subgraph IDs owned by a node."""
        with self._lock:
            return {sg for sg, owner in self._owners.items() if owner == node_id}

    def all_owners(self) -> dict[str, str]:
        with self._lock:
            return dict(self._owners)
