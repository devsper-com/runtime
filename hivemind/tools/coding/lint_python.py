"""Lint Python code using ruff if available."""

import subprocess
import tempfile
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class LintPythonTool(Tool):
    """Lint Python code. Uses ruff if installed; otherwise returns a message."""

    name = "lint_python"
    description = "Lint Python code with ruff. Returns lint output or suggests installing ruff."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python code to lint"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if code is None:
            return "Error: code is required"
        if not isinstance(code, str):
            code = str(code)
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name
            try:
                result = subprocess.run(
                    ["ruff", "check", path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                out = result.stdout or result.stderr or ""
                if result.returncode == 0 and not out:
                    return "No issues found."
                return out.strip() or "No output from ruff."
            finally:
                Path(path).unlink(missing_ok=True)
        except FileNotFoundError:
            return "ruff not installed. Install with: pip install ruff"
        except Exception as e:
            return f"Error: {e}"


register(LintPythonTool())
