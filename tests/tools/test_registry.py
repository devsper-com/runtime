"""Tests for the tool registry."""

import pytest

from hivemind.tools.base import Tool
from hivemind.tools.registry import register, get, list_tools


class _DummyTool(Tool):
    name = "_dummy_test"
    description = "For testing"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> str:
        return "ok"


def test_register_and_get():
    t = _DummyTool()
    register(t)
    assert get("_dummy_test") is t
    assert get("nonexistent") is None


def test_list_tools_includes_registered():
    t = _DummyTool()
    register(t)
    tools = list_tools()
    assert any(tool.name == "_dummy_test" for tool in tools)
