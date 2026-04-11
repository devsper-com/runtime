"""
devsper tool system: base, registry, tool_runner, and all categorized tools.

Importing this package triggers registration of all tools via category __init__.py.
"""

from devsper.core.tools.loader import bootstrap_tool_packages
from devsper.tools.base import Tool
from devsper.tools.registry import register, get, list_tools
from devsper.tools.tool_runner import run_tool

bootstrap_tool_packages(
    [
        "devsper.tools.filesystem",
        "devsper.tools.research",
        "devsper.tools.coding",
        "devsper.tools.data",
        "devsper.tools.math",
        "devsper.tools.system",
        "devsper.tools.documents",
        "devsper.tools.knowledge",
        "devsper.tools.default",
        "devsper.tools.research_advanced",
        "devsper.tools.code_intelligence",
        "devsper.tools.data_science",
        "devsper.tools.experiments",
        "devsper.tools.flagship",
        "devsper.tools.memory",
        "devsper.tools.hitl_request",
        "devsper.tools.workspace",
        "devsper.tools.forge",
    ]
)

# Load plugins from entry_points (devsper.plugins)
try:
    from devsper.plugins.plugin_loader import load_plugins
    load_plugins()
except Exception:
    pass

__all__ = ["Tool", "register", "get", "list_tools", "run_tool"]
