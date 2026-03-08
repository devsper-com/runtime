"""Delete a memory entry by id."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.memory.memory_store import get_default_store


class DeleteMemoryTool(Tool):
    name = "delete_memory"
    description = "Delete a stored memory entry by its id."
    input_schema = {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "Id of the memory to delete"},
        },
        "required": ["memory_id"],
    }

    def run(self, **kwargs) -> str:
        memory_id = kwargs.get("memory_id")
        if not memory_id or not isinstance(memory_id, str):
            return "Error: memory_id must be a non-empty string"
        store = get_default_store()
        deleted = store.delete(memory_id)
        return "Deleted." if deleted else "Memory not found."
