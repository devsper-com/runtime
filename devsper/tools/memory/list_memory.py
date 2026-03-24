"""List stored memory entries with optional type filter."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.memory.context import get_effective_memory_namespace, get_effective_memory_store
from devsper.memory.memory_types import MemoryType


class ListMemoryTool(Tool):
    name = "list_memory"
    description = "List stored memory entries. Optionally filter by type and limit."
    input_schema = {
        "type": "object",
        "properties": {
            "memory_type": {"type": "string", "description": "Optional: episodic, semantic, artifact, research"},
            "limit": {"type": "integer", "description": "Max entries to return (default 20)"},
        },
    }

    def run(self, **kwargs) -> str:
        store = get_effective_memory_store()
        ns = get_effective_memory_namespace()
        mt = kwargs.get("memory_type")
        limit = kwargs.get("limit", 20)
        if not isinstance(limit, int) or limit < 1:
            limit = 20
        try:
            memory_type = MemoryType(mt.lower()) if mt else None
        except (ValueError, AttributeError):
            memory_type = None
        records = store.list_memory(memory_type=memory_type, limit=limit, namespace=ns)
        if not records:
            return "No memory entries."
        lines = [f"- {r.id} [{r.memory_type.value}] {r.content[:150]}{'...' if len(r.content) > 150 else ''}" for r in records]
        return "\n".join(lines)
