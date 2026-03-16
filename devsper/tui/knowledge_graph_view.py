"""
Knowledge graph viewer: list entities and relationships from the knowledge graph.
Builds KG from default memory store on demand.
"""

from textual.widgets import Static


class KnowledgeGraphView(Static):
    """Shows entities and edges from the knowledge graph (built from memory)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._text = "(knowledge graph)\n\nRefresh to build from memory."

    def load_from_memory(self, limit_entities: int = 40, limit_edges: int = 30) -> None:
        """Build KG from default store and display entities + edges."""
        try:
            from devsper.knowledge.knowledge_graph import KnowledgeGraph
            from devsper.memory.memory_store import get_default_store

            store = get_default_store()
            kg = KnowledgeGraph(store=store)
            kg.build_from_memory()
            g = kg.graph
            entities = []
            for nid, data in g.nodes(data=True):
                kind = data.get("kind", "?")
                label = (data.get("label") or nid)[:60]
                entities.append(f"  {nid[:40]} [{kind}] {label}")
            edges = []
            for u, v, data in list(g.edges(data=True))[:limit_edges]:
                et = data.get("type", "")
                edges.append(f"  {u[:25]} --[{et}]--> {v[:25]}")
            if not entities and not edges:
                self._text = "(no entities)\n\nAdd memory and refresh."
            else:
                self._text = "Entities:\n" + "\n".join(entities[:limit_entities])
                if edges:
                    self._text += "\n\nEdges:\n" + "\n".join(edges)
        except Exception as e:
            self._text = f"(error: {e})"
        self.update(self._text)

    def on_mount(self) -> None:
        self.update(self._text)
