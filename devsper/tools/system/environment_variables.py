"""List environment variable names (and optionally values)."""

import os

from devsper.tools.base import Tool
from devsper.tools.registry import register


class EnvironmentVariablesTool(Tool):
    """List environment variable names. Optionally include values (may be sensitive)."""

    name = "environment_variables"
    description = "List environment variable names. Optionally show values."
    input_schema = {
        "type": "object",
        "properties": {"show_values": {"type": "boolean", "description": "If true, include values"}},
        "required": [],
    }

    def run(self, **kwargs) -> str:
        show = kwargs.get("show_values", False)
        names = sorted(os.environ.keys())
        if not show:
            return "\n".join(names)
        lines = [f"{k}={os.environ[k]}" for k in names]
        return "\n".join(lines)


register(EnvironmentVariablesTool())
