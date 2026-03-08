"""Analyze code complexity: line count, cyclomatic complexity approximation, nesting."""

import ast

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class AnalyzeCodeComplexityTool(Tool):
    """Report simple complexity metrics: lines, number of branches, max nesting."""

    name = "analyze_code_complexity"
    description = "Analyze Python code: line count, branch count, nesting depth."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python code to analyze"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return "Error: code must be a non-empty string"
        try:
            tree = ast.parse(code)
            lines = len(code.splitlines())
            branches = 0
            max_nest = 0

            def visit(node: ast.AST, depth: int) -> None:
                nonlocal branches, max_nest
                max_nest = max(max_nest, depth)
                if isinstance(node, (ast.If, ast.While, ast.For, ast.With, ast.Try, ast.Assert)):
                    branches += 1
                if isinstance(node, ast.comprehension):
                    branches += 1
                for child in ast.iter_child_nodes(node):
                    visit(child, depth + 1)

            visit(tree, 0)
            return f"Lines: {lines}\nBranches (approx): {branches}\nMax nesting depth: {max_nest}"
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(AnalyzeCodeComplexityTool())
