"""Detect simple design patterns in Python code: singleton-like, context manager, etc."""

import ast
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DesignPatternDetectorTool(Tool):
    """
    Detect heuristic design patterns: class with __enter__/__exit__, base class usage, etc.
    """

    name = "design_pattern_detector"
    description = "Detect simple design patterns in Python code (context manager, inheritance)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file or directory"},
            "max_results": {"type": "integer", "description": "Max results (default 30)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_results = kwargs.get("max_results", 30)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_results, int) or max_results < 1:
            max_results = 30
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: path not found: {path}"
        files = [p] if p.is_file() and p.suffix == ".py" else list(p.rglob("*.py")) if p.is_dir() else []
        patterns = []
        for f in files:
            if not f.is_file():
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
                rel = str(f.relative_to(p if p.is_dir() else f.parent)).replace("\\", "/")
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        names = {n.name for n in ast.iter_child_nodes(node) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                        if "__enter__" in names and "__exit__" in names:
                            patterns.append({"file": rel, "pattern": "context_manager", "class": node.name})
                        if node.bases:
                            patterns.append({"file": rel, "pattern": "inheritance", "class": node.name, "bases": [ast.unparse(b) for b in node.bases[:3]]})
                    if len(patterns) >= max_results:
                        break
            except (SyntaxError, OSError):
                continue
            if len(patterns) >= max_results:
                break
        import json

        return json.dumps({"patterns": patterns}, indent=2)


register(DesignPatternDetectorTool())
