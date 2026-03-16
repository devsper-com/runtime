"""Run Python code in a subprocess and return stdout/stderr."""

import subprocess
import tempfile
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RunPythonTool(Tool):
    """Execute Python code in a subprocess. Returns combined stdout and stderr."""

    name = "run_python"
    description = "Run Python code string in a subprocess. Returns stdout and stderr."
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string", "description": "Python code to execute"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = kwargs.get("code")
        if not code or not isinstance(code, str):
            return "Error: code must be a non-empty string"
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                path = f.name
            try:
                result = subprocess.run(
                    ["python", path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=Path(path).parent,
                )
                out = result.stdout or ""
                err = result.stderr or ""
                if err:
                    out = out + "\n--- stderr ---\n" + err
                if result.returncode != 0:
                    out = f"[exit code {result.returncode}]\n" + out
                return out.strip() or "(no output)"
            finally:
                Path(path).unlink(missing_ok=True)
        except subprocess.TimeoutExpired:
            return "Error: execution timed out (30s)"
        except Exception as e:
            return f"Error: {e}"


register(RunPythonTool())
