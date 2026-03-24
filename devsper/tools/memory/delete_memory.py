"""Delete a memory entry by id."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.memory.context import get_effective_memory_namespace, get_effective_memory_store


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
        store = get_effective_memory_store()
        ns = get_effective_memory_namespace()
        deleted = store.delete(memory_id, namespace=ns)
        return "Deleted." if deleted else "Memory not found."
