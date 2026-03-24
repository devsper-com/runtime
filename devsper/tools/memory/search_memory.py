"""Semantic search over stored memory."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.memory.context import get_effective_memory_namespace, get_effective_memory_store
from devsper.memory.memory_index import MemoryIndex


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
        store = get_effective_memory_store()
        ns = get_effective_memory_namespace()
        index = MemoryIndex(store)
        records = index.query_memory(query, top_k=top_k, namespace=ns)
        if not records:
            return "No matching memory found."
        lines = []
        for r in records:
            lines.append(f"[{r.id}] ({r.memory_type.value}) {r.content[:300]}{'...' if len(r.content) > 300 else ''}")
        return "\n".join(lines)
