"""
Reasoning graph viewer: show reasoning nodes from the current run's reasoning store.
"""

from textual.widgets import Static


class ReasoningGraphView(Static):
    """Displays reasoning nodes (agent_id, task_id, content preview) from ReasoningStore."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reasoning_store = None

    def set_reasoning_store(self, store) -> None:
        """Set the ReasoningStore to display (e.g. from app or swarm)."""
        self._reasoning_store = store

    def load_from_store(self) -> None:
        """Load nodes from the configured store and update display."""
        if self._reasoning_store is None:
            self.update("(Reasoning graph)\n\nNo reasoning store for this run.")
            return
        try:
            nodes = self._reasoning_store.query_nodes(limit=30)
            if not nodes:
                self.update("(Reasoning graph)\n\nNo reasoning nodes yet.")
                return
            lines = ["(Reasoning graph)", ""]
            for n in nodes[:20]:
                preview = (n.content or "")[:80].replace("\n", " ")
                if len(n.content or "") > 80:
                    preview += "..."
                lines.append(f"  {n.id} [{n.agent_id}] task={n.task_id}")
                lines.append(f"    {preview}")
                lines.append("")
            self.update("\n".join(lines))
        except Exception as e:
            self.update(f"(Reasoning graph)\n\nError: {e}")
