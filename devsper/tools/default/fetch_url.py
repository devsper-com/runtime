from __future__ import annotations

from devsper.tools.base import Tool
from devsper.tools.registry import register


class FetchURLTool(Tool):
    name = "fetch_url"
    description = "Fetch a URL and return extracted text content."
    category = "research"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Trim output to N chars (default 8000)"},
        },
        "required": ["url"],
    }

    def run(self, **kwargs) -> str:
        url = str(kwargs.get("url") or "").strip()
        max_chars = int(kwargs.get("max_chars") or 8000)
        if not url:
            return "Error: url is required."
        max_chars = max(500, min(50000, max_chars))
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, timeout=15, headers={"User-Agent": "devsper/1.0"})
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            if "text/html" in ctype:
                soup = BeautifulSoup(resp.text, "html.parser")
                for x in soup(["script", "style", "noscript"]):
                    x.decompose()
                text = " ".join(soup.get_text(separator=" ").split())
            else:
                text = resp.text
            return (text or "")[:max_chars]
        except Exception as e:
            return f"Error: fetch_url failed: {e}"


register(FetchURLTool())

