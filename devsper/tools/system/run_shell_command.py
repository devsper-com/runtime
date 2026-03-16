"""Run a shell command and return stdout/stderr."""

import subprocess
import shlex

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RunShellCommandTool(Tool):
    """Execute a shell command and return combined stdout and stderr."""

    name = "run_shell_command"
    description = "Run a shell command. Returns stdout and stderr. Timeout 60s."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "timeout_seconds": {"type": "integer", "description": "Timeout in seconds (default 60)"},
        },
        "required": ["command"],
    }

    def run(self, **kwargs) -> str:
        command = kwargs.get("command")
        timeout = kwargs.get("timeout_seconds", 60)
        if not command or not isinstance(command, str):
            return "Error: command must be a non-empty string"
        if not isinstance(timeout, int) or timeout < 1:
            timeout = 60
        try:
            result = subprocess.run(
                shlex.split(command) if isinstance(command, str) else [command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = result.stdout or ""
            err = result.stderr or ""
            if err:
                out = out + "\n--- stderr ---\n" + err
            if result.returncode != 0:
                out = f"[exit {result.returncode}]\n" + out
            return out.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"


register(RunShellCommandTool())
