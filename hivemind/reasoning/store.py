"""
Reasoning store: in-memory store backed by a ReasoningGraph. Used by swarm/agents.

Thread-safe for concurrent add_node from executor's worker pool (asyncio run_in_executor).
"""

import secrets
import threading
from hivemind.reasoning.graph import ReasoningGraph
from hivemind.reasoning.nodes import ReasoningNode


def _short_id() -> str:
    return secrets.token_hex(4)


class ReasoningStore:
    """Store for reasoning nodes. Wraps ReasoningGraph; agents write/query via this."""

    def __init__(self) -> None:
        self._graph = ReasoningGraph()
        self._lock = threading.Lock()

    @property
    def graph(self) -> ReasoningGraph:
        return self._graph

    def add_node(
        self,
        agent_id: str,
        task_id: str,
        content: str,
        dependencies: list[str] | None = None,
        node_id: str | None = None,
    ) -> ReasoningNode:
        """Create and add a reasoning node. Returns the new node. Thread-safe for concurrent workers."""
        nid = node_id or _short_id()
        node = ReasoningNode(
            id=nid,
            agent_id=agent_id,
            task_id=task_id,
            content=content,
            dependencies=dependencies or [],
        )
        with self._lock:
            self._graph.add_node(node)
        return node

    def query_nodes(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[ReasoningNode]:
        """Query stored nodes by optional agent_id and/or task_id. Thread-safe."""
        with self._lock:
            return self._graph.query_nodes(
                agent_id=agent_id,
                task_id=task_id,
                limit=limit,
            )

    def get_dependencies(self, node_id: str) -> list[ReasoningNode]:
        """Return dependencies of the given node. Thread-safe."""
        with self._lock:
            return self._graph.get_dependencies(node_id)
