"""Report CPU usage (basic). Uses psutil if available, else placeholder."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class CpuUsageTool(Tool):
    """Return CPU usage percent. Uses psutil if installed."""

    name = "cpu_usage"
    description = "Get CPU usage percentage. Requires psutil or returns N/A."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> str:
        try:
            import psutil
            return f"CPU percent: {psutil.cpu_percent(interval=1)}%"
        except ImportError:
            return "psutil not installed. Install with: pip install psutil"


register(CpuUsageTool())
