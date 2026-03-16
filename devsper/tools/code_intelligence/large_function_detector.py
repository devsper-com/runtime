"""Detect large functions by line count and list them with locations."""

import ast
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class LargeFunctionDetectorTool(Tool):
    """
    List functions that exceed a line-count threshold (default 50 lines).
    """

    name = "large_function_detector"
    description = "Detect large functions by line count in Python files."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file or directory"},
            "min_lines": {"type": "integer", "description": "Minimum lines to flag (default 50)"},
            "max_results": {"type": "integer", "description": "Max results (default 25)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        min_lines = kwargs.get("min_lines", 50)
        max_results = kwargs.get("max_results", 25)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(min_lines, int) or min_lines < 1:
            min_lines = 50
        if not isinstance(max_results, int) or max_results < 1:
            max_results = 25
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: path not found: {path}"
        files = [p] if p.is_file() and p.suffix == ".py" else list(p.rglob("*.py")) if p.is_dir() else []
        large = []
        for f in files:
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
                rel = str(f.relative_to(p if p.is_dir() else f.parent)).replace("\\", "/")
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end = node.end_lineno or node.lineno
                        line_count = end - node.lineno + 1
                        if line_count >= min_lines:
                            large.append({"file": rel, "function": node.name, "lines": line_count, "line_start": node.lineno})
                    if len(large) >= max_results:
                        break
            except (SyntaxError, OSError):
                continue
            if len(large) >= max_results:
                break
        if not large:
            return f"No functions with >= {min_lines} lines found."
        import json

        return json.dumps({"large_functions": large}, indent=2)


register(LargeFunctionDetectorTool())
