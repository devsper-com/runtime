"""Generate skeleton unit test code for a function (template-based)."""

import ast

from devsper.tools.base import Tool
from devsper.tools.registry import register


class GenerateUnitTestsTool(Tool):
    """Generate a minimal pytest-style test skeleton for a function. No LLM."""

    name = "generate_unit_tests"
    description = "Generate skeleton pytest tests for a function. Uses function name and params."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python function or module code"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return "Error: code must be a non-empty string"
        try:
            tree = ast.parse(code)
            tests = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    params = [a.arg for a in node.args.args if a.arg != "self"]
                    test_name = f"test_{node.name}"
                    args_str = ", ".join(repr(f"arg_{p}") for p in params)
                    tests.append(f"def {test_name}():\n    assert {node.name}({args_str}) is not None  # TODO\n")
            if not tests:
                return "No function definitions found in code."
            return "import pytest\n\n" + "\n".join(tests)
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Error: {e}"


register(GenerateUnitTestsTool())
