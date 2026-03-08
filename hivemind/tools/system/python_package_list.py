"""List installed Python packages (pip list)."""

import subprocess

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class PythonPackageListTool(Tool):
    """Run pip list and return output."""

    name = "python_package_list"
    description = "List installed Python packages (pip list)."
    input_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Max lines to return (default 100)"}},
        "required": [],
    }

    def run(self, **kwargs) -> str:
        limit = kwargs.get("limit", 100)
        if not isinstance(limit, int) or limit < 1:
            limit = 100
        try:
            result = subprocess.run(
                ["pip", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = result.stdout or result.stderr or ""
            lines = out.strip().splitlines()
            return "\n".join(lines[:limit])
        except FileNotFoundError:
            return "pip not found"
        except Exception as e:
            return f"Error: {e}"


register(PythonPackageListTool())
