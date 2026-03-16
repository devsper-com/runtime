"""Suggest a refactor: rename and normalize style (placeholder / heuristic)."""

import ast

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RefactorFunctionTool(Tool):
    """Suggest simple refactors: PEP8 name style, single return. No code rewrite."""

    name = "refactor_function"
    description = "Suggest refactoring tips for a function: naming, single return."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python function code"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return "Error: code must be a non-empty string"
        try:
            tree = ast.parse(code)
            tips = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not node.name.islower() and "_" not in node.name:
                        tips.append(f"Consider snake_case for function name: {node.name}")
                    returns = sum(1 for n in ast.walk(node) if isinstance(n, ast.Return))
                    if returns > 1:
                        tips.append("Multiple returns: consider single exit point.")
            return "\n".join(tips) if tips else "No refactor suggestions."
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(RefactorFunctionTool())
