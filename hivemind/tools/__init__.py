"""
Hivemind tool system: base, registry, tool_runner, and all categorized tools.

Importing this package triggers registration of all tools via category __init__.py.
"""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register, get, list_tools
from hivemind.tools.tool_runner import run_tool

from hivemind.tools import filesystem
from hivemind.tools import research
from hivemind.tools import coding
from hivemind.tools import data
from hivemind.tools import math as math_tools
from hivemind.tools import system
from hivemind.tools import documents
from hivemind.tools import knowledge
from hivemind.tools import research_advanced
from hivemind.tools import code_intelligence
from hivemind.tools import data_science
from hivemind.tools import experiments
from hivemind.tools import flagship
from hivemind.tools import memory

__all__ = ["Tool", "register", "get", "list_tools", "run_tool"]
