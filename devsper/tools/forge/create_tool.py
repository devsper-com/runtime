"""
CreateToolTool — lets agents synthesize and register new tools at runtime.

Agents invoke this when no existing tool can handle a subtask.
"""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CreateToolTool(Tool):
    """Synthesize and register a new tool at runtime."""

    name = "create_tool"
    description = (
        "Synthesize and register a new tool at runtime when no existing tool handles a need. "
        "Describe what the tool should do and it will be created, validated, and immediately available."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "What the tool should do",
            },
            "example_input": {
                "type": "object",
                "description": "Example kwargs the tool will receive",
            },
        },
        "required": ["description"],
    }
    category = "forge"

    def run(self, **kwargs) -> str:
        from devsper.forge.tool_forge import ToolForge

        forge = ToolForge()
        result = forge.synthesize(
            kwargs["description"],
            kwargs.get("example_input", {}),
        )
        if result.success:
            return json.dumps({
                "status": "created",
                "tool_name": result.tool_name,
                "message": f"Tool '{result.tool_name}' created and registered. You can now use it.",
            })
        return json.dumps({
            "status": "failed",
            "error": result.error,
        })


register(CreateToolTool())
