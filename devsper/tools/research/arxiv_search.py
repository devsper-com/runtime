"""Search the arXiv API for papers."""

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ArxivSearchTool(Tool):
    """Search arXiv for papers by query. Returns titles, authors, abstracts, and IDs."""

    name = "arxiv_search"
    description = "Search arXiv. Returns paper titles, authors, abstracts, and arxiv IDs."
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
            url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
            })
            req = urllib.request.Request(url, headers={"User-Agent": "devsper/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            lines = []
            for e in entries:
                id_el = e.find("atom:id", ns)
                title_el = e.find("atom:title", ns)
                summary_el = e.find("atom:summary", ns)
                authors = [a.find("atom:name", ns).text for a in e.findall("atom:author", ns) if a.find("atom:name", ns) is not None]
                arxiv_id = (id_el.text or "").split("/")[-1] if id_el is not None else ""
                title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
                abstract = (summary_el.text or "").strip().replace("\n", " ")[:500] if summary_el is not None else ""
                lines.append(f"ID: {arxiv_id}\nTitle: {title}\nAuthors: {', '.join(authors)}\nAbstract: {abstract}...")
            return "\n\n---\n\n".join(lines) if lines else "No results found."
        except Exception as e:
            return f"Error: {e}"


register(ArxivSearchTool())
