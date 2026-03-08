"""Summarize stored memory (e.g. by type or recent N)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.memory.memory_store import get_default_store
from hivemind.memory.memory_types import MemoryType


class SummarizeMemoryTool(Tool):
    name = "summarize_memory"
    description = "Summarize stored memory: counts by type and optional short list of recent entries."
    input_schema = {
        "type": "object",
        "properties": {
            "memory_type": {"type": "string", "description": "Optional: episodic, semantic, artifact, research"},
            "limit": {"type": "integer", "description": "Include up to N recent entries in summary (default 5)"},
        },
    }

    def run(self, **kwargs) -> str:
        store = get_default_store()
        mt = kwargs.get("memory_type")
        limit = kwargs.get("limit", 5)
        if not isinstance(limit, int) or limit < 0:
            limit = 5
        try:
            memory_type = MemoryType(mt.lower()) if mt else None
        except (ValueError, AttributeError):
            memory_type = None
        records = store.list_memory(memory_type=memory_type, limit=1000)
        total = len(records)
        by_type: dict[str, int] = {}
        for r in records:
            k = r.memory_type.value
            by_type[k] = by_type.get(k, 0) + 1
        lines = [f"Total: {total} entries.", "By type: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items()))]
        if limit > 0 and records:
            lines.append(f"\nRecent (up to {limit}):")
            for r in records[:limit]:
                lines.append(f"  - [{r.memory_type.value}] {r.content[:100]}{'...' if len(r.content) > 100 else ''}")
        return "\n".join(lines)
