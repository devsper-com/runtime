"""
Reasoning graph: DAG of reasoning nodes with add_node, query_nodes, get_dependencies.
"""

import networkx as nx

from devsper.reasoning.nodes import ReasoningNode


class ReasoningGraph:
    """DAG of reasoning nodes. Supports add_node, query_nodes, get_dependencies."""

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: dict[str, ReasoningNode] = {}

    def add_node(self, node: ReasoningNode) -> None:
        """Add a reasoning node and its dependency edges."""
        self._nodes[node.id] = node
        self._graph.add_node(node.id)
        for dep_id in node.dependencies:
            if dep_id in self._nodes:
                self._graph.add_edge(dep_id, node.id)

    def query_nodes(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
    ) -> list[ReasoningNode]:
        """Return nodes matching optional agent_id and/or task_id, most recent first."""
        out: list[ReasoningNode] = []
        for n in self._nodes.values():
            if agent_id is not None and n.agent_id != agent_id:
                continue
            if task_id is not None and n.task_id != task_id:
                continue
            out.append(n)
        out.sort(key=lambda x: x.timestamp, reverse=True)
        return out[:limit]

    def get_dependencies(self, node_id: str) -> list[ReasoningNode]:
        """Return all reasoning nodes that the given node depends on."""
        if node_id not in self._nodes:
            return []
        pred_ids = list(self._graph.predecessors(node_id))
        return [self._nodes[pid] for pid in pred_ids if pid in self._nodes]

    def get_node(self, node_id: str) -> ReasoningNode | None:
        """Return the reasoning node with the given id, or None."""
        return self._nodes.get(node_id)

    def get_successors(self, node_id: str) -> list[ReasoningNode]:
        """Return nodes that depend on the given node."""
        if node_id not in self._nodes:
            return []
        succ_ids = list(self._graph.successors(node_id))
        return [self._nodes[sid] for sid in succ_ids if sid in self._nodes]
