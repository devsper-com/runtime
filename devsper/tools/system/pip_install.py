"""Install a package with pip."""

import subprocess

from devsper.tools.base import Tool
from devsper.tools.registry import register


class PipInstallTool(Tool):
    """Install a package using pip. Returns pip output."""

    name = "pip_install"
    description = "Install a package with pip (e.g. pip install <package>)."
    input_schema = {
        "type": "object",
        "properties": {"package": {"type": "string", "description": "Package name to install"}},
        "required": ["package"],
    }

    def run(self, **kwargs) -> str:
        package = kwargs.get("package")
        if not package or not isinstance(package, str):
            return "Error: package must be a non-empty string"
        try:
            result = subprocess.run(
                ["pip", "install", package],
                capture_output=True,
                text=True,
                timeout=120,
            )
            out = result.stdout or ""
            err = result.stderr or ""
            if err:
                out = out + "\n" + err
            if result.returncode != 0:
                out = f"[exit {result.returncode}]\n" + out
            return out.strip() or "Done"
        except subprocess.TimeoutExpired:
            return "Error: pip install timed out"
        except Exception as e:
            return f"Error: {e}"


register(PipInstallTool())
