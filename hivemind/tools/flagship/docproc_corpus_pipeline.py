"""Convert a directory of PDFs/DOCX/PPTX into a structured research corpus (discover → extract → markdown → sections → JSON)."""

import json
import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown, DOCPROC_EXTENSIONS


def _extract_sections(markdown: str) -> list[dict]:
    """Extract sections from markdown (headers and following content)."""
    sections = []
    current = {"title": "", "content": "", "word_count": 0}
    for line in markdown.splitlines():
        if line.startswith("#"):
            if current["title"] or current["content"]:
                current["word_count"] = len(current["content"].split())
                sections.append(current)
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            current = {"title": title, "content": "", "word_count": 0}
        else:
            current["content"] = (current["content"] + "\n" + line).strip()
    if current["title"] or current["content"]:
        current["word_count"] = len(current["content"].split())
        sections.append(current)
    return sections


def _extract_citations(text: str) -> list[str]:
    """Heuristic citation extraction."""
    refs = []
    refs.extend(re.findall(r"\[\d+(?:\s*[-–,]\s*\d+)*\]", text))
    refs.extend(re.findall(r"\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)", text))
    return list(dict.fromkeys(refs))


class DocprocCorpusPipelineTool(Tool):
    """
    Convert a directory of PDF/DOCX/PPTX into a structured research dataset:
    discover files → docproc extraction → markdown → sections → structured JSON corpus.
    """

    name = "docproc_corpus_pipeline"
    description = "Convert a directory of PDFs/DOCX/PPTX into a structured research dataset (markdown, sections, word counts, citations)."
    input_schema = {
        "type": "object",
        "properties": {"directory": {"type": "string", "description": "Path to directory containing documents"}},
        "required": ["directory"],
    }

    def run(self, **kwargs) -> str:
        directory = kwargs.get("directory")
        if not directory or not isinstance(directory, str):
            return "Error: directory must be a non-empty string"
        root = Path(directory).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: directory not found: {directory}"

        files = []
        for ext in DOCPROC_EXTENSIONS:
            files.extend(root.rglob(f"*{ext}"))
        files = [f for f in files if f.is_file()][:50]

        corpus = []
        for path in files:
            content, err = run_docproc_to_markdown(str(path))
            if err:
                corpus.append({"path": str(path.name), "error": err, "title": path.stem, "sections": [], "word_count": 0, "citations": []})
                continue
            md = content or ""
            sections = _extract_sections(md)
            citations = _extract_citations(md)
            word_count = sum(s.get("word_count", 0) for s in sections) or len(md.split())
            title = path.stem
            if sections and sections[0].get("title"):
                title = sections[0]["title"][:200]
            corpus.append({
                "title": title,
                "path": str(path.name),
                "sections": [{"title": s["title"], "word_count": s["word_count"]} for s in sections],
                "word_count": word_count,
                "citations": citations[:30],
            })

        return json.dumps({"documents": corpus, "total_files": len(files)}, indent=2)


register(DocprocCorpusPipelineTool())
