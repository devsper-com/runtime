"""Extract function names and signatures from Python code."""

import ast

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ExtractFunctionsTool(Tool):
    """List function names and their parameter names from Python code."""

    name = "extract_functions"
    description = "Extract function names and parameter lists from Python code."
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
                    args = [a.arg for a in node.args.args]
                    result.append(f"{node.name}({', '.join(args)})")
            return "\n".join(result) if result else "No functions found."
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(ExtractFunctionsTool())
