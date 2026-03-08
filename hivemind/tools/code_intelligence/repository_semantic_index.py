"""Build a semantic-style index: modules and their docstrings / first line summary."""

import ast
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class RepositorySemanticIndexTool(Tool):
    """
    Index modules with docstrings and first-line summaries for semantic search (keyword match).
    """

    name = "repository_semantic_index"
    description = "Build a semantic index of a repo: module docstrings and summaries."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path to index"},
            "max_files": {"type": "integer", "description": "Max files to index (default 100)"},
        },
        "required": ["path"],
    }

    def _extract_summary(self, p: Path) -> dict:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
            doc = ast.get_docstring(tree)
            first_line = text.strip().split("\n")[0][:80] if text.strip() else ""
            return {"docstring": (doc or "")[:300], "first_line": first_line}
        except (SyntaxError, OSError):
            return {"docstring": "", "first_line": ""}

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_files = kwargs.get("max_files", 100)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_files, int) or max_files < 1:
            max_files = 100
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        entries = []
        for p in root.rglob("*.py"):
            if len(entries) >= max_files:
                break
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            summary = self._extract_summary(p)
            if summary["docstring"] or summary["first_line"]:
                entries.append({"file": str(rel), **summary})
        import json

        return json.dumps({"root": str(root), "entries": entries}, indent=2)


register(RepositorySemanticIndexTool())
