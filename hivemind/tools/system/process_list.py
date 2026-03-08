"""List running processes. Uses psutil if available."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ProcessListTool(Tool):
    """List running processes (pid, name). Uses psutil; limited to first N."""

    name = "process_list"
    description = "List running processes. Requires psutil. Returns pid and name for first N."
    input_schema = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Max processes to list (default 20)"}},
        "required": [],
    }

    def run(self, **kwargs) -> str:
        try:
            import psutil
        except ImportError:
            return "psutil not installed. Install with: pip install psutil"
        limit = kwargs.get("limit", 20)
        if not isinstance(limit, int) or limit < 1:
            limit = 20
        try:
            procs = list(psutil.process_iter(["pid", "name"]))[:limit]
            lines = [f"{p.info.get('pid')} {p.info.get('name', '')}" for p in procs]
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(ProcessListTool())
