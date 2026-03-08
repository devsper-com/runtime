"""Return basic system information."""

import platform
import sys

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class SystemInfoTool(Tool):
    """Return system info: OS, machine, Python version."""

    name = "system_info"
    description = "Get system information: OS, machine, Python version."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> str:
        return (
            f"system = {platform.system()}\n"
            f"machine = {platform.machine()}\n"
            f"processor = {platform.processor() or 'N/A'}\n"
            f"python = {sys.version}"
        )


register(SystemInfoTool())
