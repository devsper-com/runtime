"""DuckDuckGo search via duckduckgo-search package."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class DuckDuckGoSearchTool(Tool):
    """Search using DuckDuckGo. Requires duckduckgo-search package."""

    name = "duckduckgo_search"
    description = "Search DuckDuckGo for a query. Returns titles, snippets, and URLs."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 5)"},
        },
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 5)
        if not query or not isinstance(query, str):
            return "Error: query must be a non-empty string"
        if not isinstance(max_results, int) or max_results < 1:
            max_results = 5
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return "No results found."
            lines = [f"- {r.get('title', '')} | {r.get('href', '')}\n  {r.get('body', '')}" for r in results]
            return "\n\n".join(lines)
        except ImportError:
            return "Error: Install duckduckgo-search (pip install duckduckgo-search)."
        except Exception as e:
            return f"Error: {e}"


register(DuckDuckGoSearchTool())
