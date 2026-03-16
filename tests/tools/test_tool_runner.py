"""Tests for the tool runner."""

import pytest

from devsper.tools.tool_runner import run_tool
from devsper.tools.registry import register
from devsper.tools.base import Tool


class _EchoTool(Tool):
    name = "_echo_test"
    description = "Echo"
    input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def run(self, **kwargs) -> str:
        return str(kwargs.get("message", ""))


def test_run_tool_valid():
    register(_EchoTool())
    out = run_tool("_echo_test", {"message": "hello"})
    assert out == "hello"


def test_run_tool_missing_name():
    out = run_tool("_nonexistent_tool_xyz", {})
    assert "not found" in out.lower()


def test_run_tool_validation_error():
    register(_EchoTool())
    out = run_tool("_echo_test", {})
    assert "validation" in out.lower() or "missing" in out.lower()


def test_run_tool_exception():
    class _BombTool(Tool):
        name = "_bomb_test"
        description = "Bomb"
        input_schema = {"type": "object", "properties": {}, "required": []}

        def run(self, **kwargs) -> str:
            raise ValueError("boom")

    register(_BombTool())
    out = run_tool("_bomb_test", {})
    assert "Tool error" in out or "boom" in out
