"""Web search using DuckDuckGo when duckduckgo-search is available."""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class WebSearchTool(Tool):
    """Search the web. Uses DuckDuckGo when the duckduckgo-search package is installed."""

    name = "web_search"
    description = "Search the web for a query. Returns titles and snippets. Requires duckduckgo-search."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results to return (default 5)"},
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
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                lines.append(f"{i}. {title}\n   {body}\n   {href}")
            return "\n\n".join(lines)
        except ImportError:
            return "Error: Install duckduckgo-search (pip install duckduckgo-search) for web search."
        except Exception as e:
            return f"Error: {e}"


register(WebSearchTool())
