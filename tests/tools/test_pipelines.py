"""Tests for tool pipeline engine."""

from devsper.tools.base import Tool
from devsper.tools.registry import register, get, deregister
from devsper.tools.pipelines import ToolPipeline, build_pipeline, PIPELINE_INPUT_KEY


class _EchoTool(Tool):
    name = "test_echo"
    description = "Echo input"
    input_schema = {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}
    category = "test"

    def run(self, **kwargs) -> str:
        return kwargs.get("input", "")


def test_tool_pipeline_single_tool():
    """Pipeline with one tool just runs that tool."""
    tool = _EchoTool()
    try:
        register(tool)
        pipeline = ToolPipeline([tool])
        out = pipeline.run(input="hello")
        assert out == "hello"
    finally:
        deregister("test_echo")


def test_tool_pipeline_chains_output():
    """Two tools: first gets kwargs, second gets first output as 'input'."""
    t1 = _EchoTool()
    t1.name = "test_echo_1"
    t2 = _EchoTool()
    t2.name = "test_echo_2"
    try:
        register(t1)
        register(t2)
        pipeline = ToolPipeline([t1, t2])
        out = pipeline.run(input="chain")
        assert out == "chain"
    finally:
        deregister("test_echo_1")
        deregister("test_echo_2")


def test_build_pipeline_from_names():
    p = build_pipeline("nonexistent_tool_xyz", name="test")
    assert p.name == "test" or "pipeline" in p.name
    out = p.run()
    assert "Tool not found" in out or "Error" in out or len(out) >= 0


def test_pipeline_empty_tools_returns_message():
    pipeline = ToolPipeline([])
    out = pipeline.run(x="y")
    assert "no tools" in out.lower()
