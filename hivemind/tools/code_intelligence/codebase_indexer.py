"""Index a codebase: list modules, files, and top-level symbols (functions/classes)."""

import ast
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class CodebaseIndexerTool(Tool):
    """
    Build a simple index of a Python codebase: files, modules, and top-level function/class names.
    """

    name = "codebase_indexer"
    description = "Index a Python codebase: list files and top-level functions/classes."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path to index"},
            "max_depth": {"type": "integer", "description": "Max directory depth (default 5)"},
            "extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File extensions to include (default ['.py'])",
            },
        },
        "required": ["path"],
    }

    def _index_file(self, p: Path) -> list[str]:
        symbols = []
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.col_offset == 0:
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        symbols.append(f"{kind}:{node.name}")
        except (SyntaxError, OSError):
            pass
        return symbols

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_depth = kwargs.get("max_depth", 5)
        extensions = kwargs.get("extensions") or [".py"]
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_depth, int) or max_depth < 1:
            max_depth = 5
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        index = []
        for depth, _ in enumerate(root.rglob("*")):
            if depth > 1000:
                break
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in extensions:
                rel = p.relative_to(root)
                if len(rel.parts) > max_depth:
                    continue
                symbols = self._index_file(p)
                index.append({"file": str(rel), "symbols": symbols})
        import json

        return json.dumps({"root": str(root), "index": index[:200]}, indent=2)


register(CodebaseIndexerTool())
