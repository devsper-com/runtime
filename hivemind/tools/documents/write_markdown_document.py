"""Write a structured Markdown document with optional references section."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


def _format_ref_md(ref: dict, index: int) -> str:
    """Format one reference as a Markdown list item."""
    authors = ref.get("authors") or ref.get("author") or "Unknown"
    title = ref.get("title") or ""
    year = ref.get("year") or ""
    journal = ref.get("journal")
    url = ref.get("url")
    parts = [f"**{authors} ({year})**. *{title}*."]
    if journal:
        parts.append(f" {journal}.")
    if url:
        parts.append(f" [{url}]({url})")
    return "- " + " ".join(parts).strip()


class WriteMarkdownDocumentTool(Tool):
    """Write a structured Markdown document with optional references. Use [^1] or [Author (Year)] in content."""

    name = "write_markdown_document"
    description = (
        "Write a structured Markdown document with optional references. "
        "Use [1] / Author (Year) in content; pass references array (key, authors, title, year, journal, url, publisher) for bibliography. Produces .md file."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output path (e.g. report.md)"},
            "title": {"type": "string", "description": "Document title"},
            "content": {"type": "string", "description": "Body (markdown). Use [^1] or [Author (Year)] for citations."},
            "references": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional list of refs: key, authors, title, year, journal, url, publisher",
            },
        },
        "required": ["path", "title", "content"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        title = kwargs.get("title")
        content = kwargs.get("content")
        references = kwargs.get("references")

        if not path or not isinstance(path, str) or not path.strip():
            return "Error: path must be a non-empty string"
        if not title or not isinstance(title, str):
            return "Error: title must be a non-empty string"
        if content is None:
            return "Error: content is required"
        if not isinstance(content, str):
            content = str(content)

        path = path.strip()
        if not path.endswith(".md") and not path.endswith(".markdown"):
            path = path.rstrip("/") + ".md"
        p = Path(path).resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"Error creating directory: {e}"

        parts = [f"# {title.strip()}", "", content.strip(), ""]
        if references and isinstance(references, list):
            parts.append("## References")
            parts.append("")
            for i, ref in enumerate(references):
                if not isinstance(ref, dict):
                    continue
                parts.append(_format_ref_md(ref, i))
            parts.append("")

        full = "\n".join(parts)
        try:
            p.write_text(full, encoding="utf-8")
        except Exception as e:
            return f"Error writing file: {e}"
        return f"Wrote {len(full)} characters to {p}"


register(WriteMarkdownDocumentTool())
