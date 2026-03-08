"""Add or replace tags on a memory entry."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.memory.memory_store import get_default_store
from hivemind.memory.memory_types import MemoryRecord, MemoryType
from hivemind.memory.memory_index import MemoryIndex


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
        store = get_default_store()
        record = store.retrieve(memory_id)
        if not record:
            return "Memory not found."
        new_tags = tags if replace else list(dict.fromkeys(record.tags + tags))
        updated = MemoryRecord(
            id=record.id,
            memory_type=record.memory_type,
            timestamp=record.timestamp,
            source_task=record.source_task,
            content=record.content,
            tags=new_tags,
            embedding=record.embedding,
        )
        store.store(updated)
        return f"Tags updated: {new_tags}"
