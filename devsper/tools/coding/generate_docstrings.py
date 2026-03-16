"""Add or suggest docstring placeholders for functions that lack them."""

import ast

from devsper.tools.base import Tool
from devsper.tools.registry import register


class GenerateDocstringsTool(Tool):
    """List functions missing docstrings and suggest a one-line placeholder."""

    name = "generate_docstrings"
    description = "Find functions without docstrings and suggest a placeholder docstring."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python source code"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return "Error: code must be a non-empty string"
        try:
            tree = ast.parse(code)
            result = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    doc = ast.get_docstring(node)
                    if not doc:
                        args = [a.arg for a in node.args.args]
                        result.append(f"{node.name}({', '.join(args)}): \"\"\"TODO: describe.\"\"\"")
            return "\n".join(result) if result else "All functions have docstrings."
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(GenerateDocstringsTool())
