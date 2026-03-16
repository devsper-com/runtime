"""Store a memory entry (content, type, tags, source_task)."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.memory.memory_store import get_default_store, generate_memory_id
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.memory.memory_index import MemoryIndex


class StoreMemoryTool(Tool):
    name = "store_memory"
    description = "Store a memory entry with content, type (episodic/semantic/artifact/research), optional tags and source_task."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Content to store"},
            "memory_type": {"type": "string", "description": "One of: episodic, semantic, artifact, research"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
            "source_task": {"type": "string", "description": "Optional source task id or description"},
        },
        "required": ["content"],
    }

    def run(self, **kwargs) -> str:
        content = kwargs.get("content", "")
        if not content or not isinstance(content, str):
            return "Error: content must be a non-empty string"
        try:
            mt = MemoryType((kwargs.get("memory_type") or "semantic").lower())
        except ValueError:
            return "Error: memory_type must be one of episodic, semantic, artifact, research"
        tags = kwargs.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        source_task = kwargs.get("source_task") or ""
        store = get_default_store()
        index = MemoryIndex(store)
        record = MemoryRecord(
            id=generate_memory_id(),
            memory_type=mt,
            content=content,
            tags=tags,
            source_task=source_task,
        )
        record = index.ensure_embedding(record)
        mid = store.store(record)
        return f"Stored memory id: {mid}"
