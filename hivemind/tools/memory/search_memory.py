"""Semantic search over stored memory."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.memory.memory_store import get_default_store
from hivemind.memory.memory_index import MemoryIndex


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = "Search stored memory by semantic similarity to a query text. Returns top matches."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Max number of results (default 5)"},
        },
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        if not query or not isinstance(query, str):
            return "Error: query must be a non-empty string"
        top_k = kwargs.get("top_k", 5)
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 5
        store = get_default_store()
        index = MemoryIndex(store)
        records = index.query_memory(query, top_k=top_k)
        if not records:
            return "No matching memory found."
        lines = []
        for r in records:
            lines.append(f"[{r.id}] ({r.memory_type.value}) {r.content[:300]}{'...' if len(r.content) > 300 else ''}")
        return "\n".join(lines)
