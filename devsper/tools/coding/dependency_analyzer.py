"""Analyze import dependencies in Python code."""

import ast

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DependencyAnalyzerTool(Tool):
    """List top-level import names (modules and aliases) from Python code."""

    name = "dependency_analyzer"
    description = "Extract import statements and dependency names from Python code."
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
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
                    imports.append(f"from {mod} import {names}")
            return "\n".join(imports) if imports else "No imports found."
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(DependencyAnalyzerTool())
