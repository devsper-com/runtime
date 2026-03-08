"""Format Python code using black if available, else return as-is."""

import subprocess
import tempfile
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class FormatPythonTool(Tool):
    """Format Python code. Uses black if installed, otherwise returns code unchanged."""

    name = "format_python"
    description = "Format Python code with black. Returns formatted code or original if black not installed."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python code to format"}},
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
                    ["black", "-q", path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return Path(path).read_text(encoding="utf-8")
                return code
            finally:
                Path(path).unlink(missing_ok=True)
        except FileNotFoundError:
            return code
        except Exception as e:
            return f"Error: {e}\nOriginal code:\n{code}"


register(FormatPythonTool())
