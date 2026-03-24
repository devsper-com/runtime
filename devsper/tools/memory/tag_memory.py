"""Add or replace tags on a memory entry."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.memory.context import get_effective_memory_namespace, get_effective_memory_store
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.memory.memory_index import MemoryIndex


class TagMemoryTool(Tool):
    name = "tag_memory"
    description = "Add or replace tags on an existing memory entry by id."
    input_schema = {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Id of the memory"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags to set (replaces existing if replace=true)"},
            "replace": {"type": "boolean", "description": "If true, replace existing tags; else append (default false)"},
        },
        "required": ["memory_id", "tags"],
    }

    def run(self, **kwargs) -> str:
        memory_id = kwargs.get("memory_id")
        tags = kwargs.get("tags") or []
        replace = kwargs.get("replace", False)
        if not memory_id or not isinstance(memory_id, str):
            return "Error: memory_id must be a non-empty string"
        if not isinstance(tags, list):
            tags = [str(tags)]
        tags = [str(t).strip() for t in tags if str(t).strip()]
        store = get_effective_memory_store()
        ns = get_effective_memory_namespace()
        record = store.retrieve(memory_id, namespace=ns)
        if not record:
            return "Memory not found."
        new_tags = tags if replace else list(dict.fromkeys(record.tags + tags))
        updated = record.model_copy(update={"tags": new_tags})
        store.store(updated, namespace=ns)
        return f"Tags updated: {new_tags}"
