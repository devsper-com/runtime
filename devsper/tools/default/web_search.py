from __future__ import annotations

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DefaultWebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return title/url/snippet results."
    category = "research"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results (default 5)"},
        },
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        query = str(kwargs.get("query") or "").strip()
        num_results = int(kwargs.get("num_results") or 5)
        if not query:
            return "Error: query is required."
        num_results = max(1, min(20, num_results))

        # Preferred: duckduckgo-search package.
        try:
            from duckduckgo_search import DDGS

            rows = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num_results):
                    rows.append(
                        {
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", ""),
                        }
                    )
            if rows:
                return "\n\n".join(
                    f"{i+1}. {x['title']}\nURL: {x['url']}\nSnippet: {x['snippet']}"
                    for i, x in enumerate(rows)
                )
        except Exception:
            pass

        # Fallback (best effort): lightweight DDG html endpoint.
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                timeout=12,
                headers={"User-Agent": "devsper/1.0"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            items = []
            for row in soup.select(".result")[:num_results]:
                a = row.select_one(".result__a")
                sn = row.select_one(".result__snippet")
                if not a:
                    continue
                items.append(
                    {
                        "title": a.get_text(strip=True),
                        "url": a.get("href", ""),
                        "snippet": sn.get_text(" ", strip=True) if sn else "",
                    }
                )
            if items:
                return "\n\n".join(
                    f"{i+1}. {x['title']}\nURL: {x['url']}\nSnippet: {x['snippet']}"
                    for i, x in enumerate(items)
                )
        except Exception as e:
            return f"Error: web search failed: {e}"

        return "No results found."


register(DefaultWebSearchTool())

