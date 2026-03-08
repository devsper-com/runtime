"""
Memory panel: list memory entries with tags and summaries.
"""

from textual.widgets import Static


class MemoryView(Static):
    """Displays memory entries: id, tags, content summary."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._entries: list[dict] = []

    def set_entries(self, entries: list[dict]) -> None:
        """Update entries. Each dict: id, tags (list), summary or content (str)."""
        self._entries = entries
        self._refresh_display()

    def load_from_store(self, limit: int = 20) -> None:
        """Load from default memory store."""
        try:
            from hivemind.memory.memory_store import get_default_store

            store = get_default_store()
            records = store.list_memory(limit=limit)
            self._entries = [
                {
                    "id": r.id[:8] + "…" if len(r.id) > 8 else r.id,
                    "tags": r.tags or [],
                    "summary": (r.content or "")[:120]
                    + ("…" if len(r.content or "") > 120 else ""),
                }
                for r in records
            ]
        except Exception as e:
            self._entries = [{"id": "error", "tags": [], "summary": str(e)}]
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self._entries:
            self.update("(no memory entries)\n\n[m] refresh memory")
            return
        lines = []
        for e in self._entries:
            eid = e.get("id", "?")
            tags = e.get("tags", [])
            summary = e.get("summary", e.get("content", ""))[:100]
            tag_str = ", ".join(tags[:5]) if tags else "-"
            lines.append(f"{eid} [{tag_str}]")
            lines.append(f"  {summary}")
        self.update("\n".join(lines))

    def on_mount(self) -> None:
        self.load_from_store()
