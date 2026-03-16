"""Tests for smart tool selection."""

import pytest

from devsper.tools.selector import select_tools_for_task, get_tools_for_task, _tool_category
from devsper.tools.registry import list_tools
from devsper.tools.base import Tool


def test_select_tools_for_task_top_k_zero_returns_all():
    tools = list_tools()
    if not tools:
        pytest.skip("no tools registered")
    selected = select_tools_for_task("search the web", top_k=0, enabled_categories=None)
    assert len(selected) == len(tools)


def test_select_tools_for_task_top_k_limits():
    tools = list_tools()
    if len(tools) < 3:
        pytest.skip("need at least 3 tools")
    selected = select_tools_for_task("do something", top_k=3, enabled_categories=None)
    assert len(selected) <= 3


def test_get_tools_for_task_no_config_returns_all():
    # When config has no top_k (or top_k=0), we get all tools
    class NoToolsConfig:
        tools = None
    tools = get_tools_for_task("task", config=NoToolsConfig())
    all_tools = list_tools()
    assert len(tools) == len(all_tools)


def test_tool_category_inferred_from_module():
    class FakeTool(Tool):
        name = "fake"
        description = "fake"
        input_schema = {}
        def run(self, **kwargs): return ""
    t = FakeTool()
    t.__class__.__module__ = "devsper.tools.research.foo"
    cat = _tool_category(t)
    assert cat == "research"
