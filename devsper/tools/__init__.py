"""
devsper tool system: base, registry, tool_runner, and all categorized tools.

Importing this package triggers registration of all tools via category __init__.py.
"""

from devsper.tools.base import Tool
from devsper.tools.registry import register, get, list_tools
from devsper.tools.tool_runner import run_tool

from devsper.tools import filesystem
from devsper.tools import research
from devsper.tools import coding
from devsper.tools import data
from devsper.tools import math as math_tools
from devsper.tools import system
from devsper.tools import documents
from devsper.tools import knowledge
from devsper.tools import research_advanced
from devsper.tools import code_intelligence
from devsper.tools import data_science
from devsper.tools import experiments
from devsper.tools import flagship
from devsper.tools import memory

# Load plugins from entry_points (devsper.plugins)
try:
    from devsper.plugins.plugin_loader import load_plugins
    load_plugins()
except Exception:
    pass

__all__ = ["Tool", "register", "get", "list_tools", "run_tool"]
