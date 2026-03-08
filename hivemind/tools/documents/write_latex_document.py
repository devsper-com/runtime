"""Write a structured LaTeX document with optional BibTeX references."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


def _latex_escape(s: str) -> str:
    """Escape braces for use inside BibTeX/LaTeX strings."""
    if not s:
        return ""
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bib_entry(key: str, ref: dict) -> str:
    """Build one BibTeX entry (article by default)."""
    author = ref.get("authors") or ref.get("author") or "Unknown"
    title = ref.get("title") or ""
    year = ref.get("year") or ""
    journal = ref.get("journal")
    url = ref.get("url")
    publisher = ref.get("publisher")
    author = _latex_escape(str(author))
    title = _latex_escape(str(title))
    year = _latex_escape(str(year))
    lines = [f"@article{{{key},"]
    lines.append(f"  author = {{{author}}},")
    lines.append(f"  title = {{{title}}},")
    lines.append(f"  year = {{{year}}},")
    if journal:
        lines.append(f"  journal = {{{_latex_escape(str(journal))}}},")
    if publisher:
        lines.append(f"  publisher = {{{_latex_escape(str(publisher))}}},")
    if url:
        lines.append(f"  url = {{{_latex_escape(str(url))}}},")
    lines.append("}")
    return "\n".join(lines)


class WriteLaTeXDocumentTool(Tool):
    """Write a structured LaTeX document with optional references. Use \\cite{key} in content."""

    name = "write_latex_document"
    description = (
        r"Write a structured LaTeX document with optional references. "
        r"Use \cite{key} (LaTeX) in content; pass references array (key, authors, title, year, journal, url, publisher) for bibliography. Produces .tex and .bib files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output path (e.g. report.tex)"},
            "title": {"type": "string", "description": "Document title"},
            "content": {"type": "string", "description": r"Body (LaTeX). Use \cite{key} for citations."},
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
        if not path.endswith(".tex"):
            path = path.rstrip("/") + ".tex"
        p = Path(path).resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return f"Error creating directory: {e}"

        basename = p.stem
        title_esc = _latex_escape(title)

        tex_parts = [
            "\\documentclass{article}",
            "\\begin{document}",
            "\\title{" + title_esc + "}",
            "\\maketitle",
            "",
            content.strip(),
            "",
        ]
        if references and isinstance(references, list):
            tex_parts.append("\\bibliographystyle{plain}")
            tex_parts.append("\\bibliography{" + basename + "}")
            tex_parts.append("")
        tex_parts.append("\\end{document}")
        tex_content = "\n".join(tex_parts)

        try:
            p.write_text(tex_content, encoding="utf-8")
        except Exception as e:
            return f"Error writing .tex file: {e}"

        out_msg = f"Wrote {len(tex_content)} characters to {p}"

        if references and isinstance(references, list):
            bib_path = p.with_suffix(".bib")
            bib_entries = []
            for i, ref in enumerate(references):
                if not isinstance(ref, dict):
                    continue
                key = ref.get("key") or f"ref{i+1}"
                bib_entries.append(_bib_entry(key, ref))
            if bib_entries:
                bib_content = "\n\n".join(bib_entries)
                try:
                    bib_path.write_text(bib_content, encoding="utf-8")
                except Exception as e:
                    return f"{out_msg}. Error writing .bib file: {e}"
                out_msg = f"Wrote {p} and {bib_path}. Compile with: pdflatex {basename} && bibtex {basename} && pdflatex {basename} && pdflatex {basename}."

        return out_msg


register(WriteLaTeXDocumentTool())
