"""Run a shell command and return stdout/stderr."""

import subprocess
import os

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RunShellCommandTool(Tool):
    """Execute a shell command and return combined stdout and stderr."""

    name = "run_shell_command"
    description = "Run a shell command. Uses a real shell so &&, pipes, and redirects work. Timeout 120s."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run (supports pipes, redirects)",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Timeout in seconds (default 120)",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory to run the command in (optional)",
            },
        },
        "required": ["command"],
    }

    def run(self, **kwargs) -> str:
        command = kwargs.get("command")
        timeout = kwargs.get("timeout_seconds", 120)
        workdir = kwargs.get("workdir")

        if not command or not isinstance(command, str):
            return "Error: command must be a non-empty string"
        if not isinstance(timeout, int) or timeout < 1:
            timeout = 120

        if workdir and not os.path.exists(workdir):
            return f"Error: working directory '{workdir}' does not exist"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )
            out = result.stdout or ""
            err = result.stderr or ""
            if err:
                out = out + "\n--- stderr ---\n" + err
            if result.returncode != 0:
                out = f"[exit code {result.returncode}]\n" + out
            return out.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"


register(RunShellCommandTool())
