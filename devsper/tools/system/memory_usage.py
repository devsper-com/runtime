"""Report memory usage. Uses psutil if available."""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class MemoryUsageTool(Tool):
    """Return memory usage (total, used, percent). Uses psutil if installed."""

    name = "memory_usage"
    description = "Get memory usage. Requires psutil or returns N/A."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> str:
        try:
            import psutil
            v = psutil.virtual_memory()
            return f"total = {v.total} bytes\nused = {v.used} bytes\npercent = {v.percent}%"
        except ImportError:
            return "psutil not installed. Install with: pip install psutil"


register(MemoryUsageTool())
