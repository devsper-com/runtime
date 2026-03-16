"""
Tool pipeline engine: chain tools so output of one feeds into the next.

Example: docproc → entity_extractor → knowledge_graph_builder.
Agents may invoke pipelines instead of single tools.
"""

from devsper.tools.base import Tool
from devsper.tools.registry import get
from devsper.tools.tool_runner import run_tool

# Key used to pass previous stage output into the next tool's args
PIPELINE_INPUT_KEY = "input"


class ToolPipeline:
    """
    A chain of tools. run() executes each in order; each tool's output
    is passed as PIPELINE_INPUT_KEY to the next. Initial args go to the first tool.
    """

    def __init__(self, tools: list[str] | list[Tool], name: str = "") -> None:
        """
        tools: list of tool names (str) or Tool instances. Names are resolved via registry.
        name: optional pipeline name for display/registry.
        """
        self._tool_refs: list[tuple[str, Tool | None]] = []
        for t in tools:
            if isinstance(t, Tool):
                self._tool_refs.append((t.name, t))
            else:
                self._tool_refs.append((str(t), get(str(t))))
        self.name = name or "pipeline_" + "_".join(n for n, _ in self._tool_refs[:3])

    @property
    def tools(self) -> list[Tool]:
        """Resolved list of Tool instances (skips unresolved names)."""
        return [t for _, t in self._tool_refs if t is not None]

    def run(self, **kwargs) -> str:
        """
        Run the pipeline: first tool gets kwargs; each next tool gets
        PIPELINE_INPUT_KEY set to the previous tool's string output.
        Returns the last tool's output, or an error message.
        """
        if not self._tool_refs:
            return "Pipeline has no tools."
        current_input: str | None = None
        for i, (tool_name, tool) in enumerate(self._tool_refs):
            if tool is None:
                return f"Tool not found: {tool_name}"
            if i == 0:
                args = dict(kwargs)
            else:
                args = {PIPELINE_INPUT_KEY: current_input or ""}
            result = run_tool(tool.name, args)
            if (
                result.startswith("Error:")
                or result.startswith("Tool not found:")
                or result.startswith("Validation error:")
            ):
                return result
            current_input = result
        return current_input or ""


def build_pipeline(*tool_names: str, name: str = "") -> ToolPipeline:
    """Build a pipeline from a sequence of tool names. Example: build_pipeline('docproc_corpus_pipeline', 'knowledge_graph_extractor')."""
    return ToolPipeline(list(tool_names), name=name)


class PipelineAsTool(Tool):
    """Exposes a ToolPipeline as a Tool so agents can invoke it by name."""

    def __init__(self, pipeline: ToolPipeline, description: str = "") -> None:
        self._pipeline = pipeline
        self.name = pipeline.name
        self.description = (
            description
            or f"Run pipeline: {' → '.join(n for n, _ in pipeline._tool_refs)}"
        )
        # Merge required keys from first tool if available
        first_tool = pipeline.tools[0] if pipeline.tools else None
        self.input_schema = (
            getattr(first_tool, "input_schema", {"type": "object", "properties": {}})
            if first_tool
            else {"type": "object", "properties": {}}
        )
        self.category = "pipeline"

    def run(self, **kwargs) -> str:
        return self._pipeline.run(**kwargs)
