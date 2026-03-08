"""Detect refactor candidates: long functions, high branch count, deep nesting."""

import ast
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class RefactorCandidateDetectorTool(Tool):
    """
    Detect refactor candidates: functions with many lines, many branches, or deep nesting.
    """

    name = "refactor_candidate_detector"
    description = "Detect refactor candidates: long functions, high complexity, deep nesting."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file or directory"},
            "min_lines": {"type": "integer", "description": "Flag functions with >= N lines (default 30)"},
            "min_branches": {"type": "integer", "description": "Flag functions with >= N branches (default 8)"},
        },
        "required": ["path"],
    }

    def _complexity(self, node: ast.AST) -> tuple[int, int]:
        branches = 0
        max_nest = 0

        def visit(n: ast.AST, depth: int) -> None:
            nonlocal branches, max_nest
            max_nest = max(max_nest, depth)
            if isinstance(n, (ast.If, ast.While, ast.For, ast.With, ast.Try, ast.Assert)):
                branches += 1
            if isinstance(n, ast.comprehension):
                branches += 1
            for c in ast.iter_child_nodes(n):
                visit(c, depth + 1)

        visit(node, 0)
        return branches, max_nest

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        min_lines = kwargs.get("min_lines", 30)
        min_branches = kwargs.get("min_branches", 8)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(min_lines, int) or min_lines < 1:
            min_lines = 30
        if not isinstance(min_branches, int) or min_branches < 1:
            min_branches = 8
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: path not found: {path}"
        files = [p] if p.is_file() and p.suffix == ".py" else list(p.rglob("*.py")) if p.is_dir() else []
        candidates = []
        for f in files:
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
                lines = text.splitlines()
                rel = str(f.relative_to(p if p.is_dir() else f.parent)).replace("\\", "/")
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        start, end = node.lineno, node.end_lineno or node.lineno
                        line_count = end - start + 1
                        branches, nest = self._complexity(node)
                        if line_count >= min_lines or branches >= min_branches:
                            candidates.append({"file": rel, "name": node.name, "lines": line_count, "branches": branches, "max_nesting": nest})
            except (SyntaxError, OSError):
                continue
        import json

        return json.dumps({"candidates": candidates[:40]}, indent=2)


register(RefactorCandidateDetectorTool())
