"""Look up a topic on Wikipedia using the JSON API."""

import json
import urllib.parse
import urllib.request

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class WikipediaLookupTool(Tool):
    """Fetch a Wikipedia article summary for a topic."""

    name = "wikipedia_lookup"
    description = "Get a short Wikipedia summary for a topic. Uses the Wikipedia API."
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic or article title to look up"},
        },
        "required": ["topic"],
    }

    def run(self, **kwargs) -> str:
        topic = kwargs.get("topic")
        if not topic or not isinstance(topic, str):
            return "Error: topic must be a non-empty string"
        try:
            url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
                "action": "query",
                "titles": topic.strip(),
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "format": "json",
            })
            req = urllib.request.Request(url, headers={"User-Agent": "Hivemind/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            pages = data.get("query", {}).get("pages", {})
            page = next(iter(pages.values()), None)
            if not page or page.get("missing"):
                return f"No Wikipedia article found for: {topic}"
            extract = page.get("extract", "").strip()
            return extract or "No extract available."
        except Exception as e:
            return f"Error: {e}"


register(WikipediaLookupTool())
