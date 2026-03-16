"""Fetch arXiv paper metadata and optionally download PDF URL."""

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ArxivDownloadTool(Tool):
    """Get arXiv paper metadata and PDF link by arXiv ID (e.g. 2401.12345 or 2401.12345v1)."""

    name = "arxiv_download"
    description = "Get arXiv paper metadata and PDF URL by ID. Does not download file to disk."
    input_schema = {
        "type": "object",
        "properties": {
            "arxiv_id": {"type": "string", "description": "arXiv ID (e.g. 2401.12345)"},
        },
        "required": ["arxiv_id"],
    }

    def run(self, **kwargs) -> str:
        arxiv_id = (kwargs.get("arxiv_id") or "").strip()
        if not arxiv_id:
            return "Error: arxiv_id must be a non-empty string"
        try:
            url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "devsper/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entry = root.find("atom:entry", ns)
            if entry is None:
                return f"No paper found for arXiv ID: {arxiv_id}"
            id_el = entry.find("atom:id", ns)
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns) if a.find("atom:name", ns) is not None]
            link_pdf = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    link_pdf = link.get("href")
                    break
            aid = (id_el.text or "").split("/")[-1] if id_el is not None else arxiv_id
            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
            pdf_line = f"PDF: {link_pdf}" if link_pdf else "PDF link not found"
            return f"ID: {aid}\nTitle: {title}\nAuthors: {', '.join(authors or [])}\nAbstract: {abstract}\n{pdf_line}"
        except Exception as e:
            return f"Error: {e}"


register(ArxivDownloadTool())
