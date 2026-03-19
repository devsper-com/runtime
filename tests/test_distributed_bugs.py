import pytest

from devsper.tools.registry import ToolRegistry
from devsper.tools.base import Tool, ToolError


class _TestTool(Tool):
    name = "test.echo"
    description = "Echo input"
    input_schema = {"type": "object", "properties": {"text": {"type": "string"}}}
    category = "general"

    def run(self, **kwargs) -> str:
        return str(kwargs.get("text", ""))


def test_tool_registry_serialization_round_trip():
    reg = ToolRegistry()
    reg.register(_TestTool())
    data = reg.to_dict()
    reg2 = ToolRegistry.from_dict(data)
    tools = {t.name: t for t in reg2.list()}
    assert "test.echo" in tools
    assert tools["test.echo"].run(text="hi") == "hi"


def test_tool_registry_stub_for_missing_class():
    data = {
        "tools": [
            {
                "name": "missing.tool",
                "description": "Missing",
                "category": "general",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {},
                "class_path": "nonexistent.module.Tool",
            }
        ]
    }
    reg = ToolRegistry.from_dict(data)
    tools = {t.name: t for t in reg.list()}
    assert "missing.tool" in tools
    with pytest.raises(ToolError):
        tools["missing.tool"].run()


def test_redis_memory_store_importable():
    # Smoke test: module exists and class can be imported.
    from devsper.memory.redis_memory import RedisMemoryStore  # noqa: F401

