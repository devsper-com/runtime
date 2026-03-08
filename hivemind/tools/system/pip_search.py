"""Search PyPI (pip search is deprecated; use simple message or run pip index)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class PipSearchTool(Tool):
    """Search PyPI. pip search is disabled; suggests using web or pip index versions."""

    name = "pip_search"
    description = "Search PyPI. Note: pip search is disabled; returns instructions."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query or not isinstance(query, str):
            return "Error: query must be a non-empty string"
        return (
            "pip search is disabled on PyPI. To find packages:\n"
            "1. Visit https://pypi.org/search/?q=" + query.replace(" ", "+") + "\n"
            "2. Or run: pip index versions <package> for a known package name"
        )


register(PipSearchTool())
