"""Pretty-print JSON with indentation."""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class JsonPrettyPrintTool(Tool):
    """Format JSON string with indentation for readability."""

    name = "json_pretty_print"
    description = "Pretty-print a JSON string with indentation."
    input_schema = {
        "type": "object",
        "properties": {
            "json_str": {"type": "string", "description": "JSON string to format"},
            "indent": {"type": "integer", "description": "Indent spaces (default 2)"},
        },
        "required": ["json_str"],
    }

    def run(self, **kwargs) -> str:
        json_str = kwargs.get("json_str")
        indent = kwargs.get("indent", 2)
        if json_str is None:
            return "Error: json_str is required"
        if not isinstance(indent, int) or indent < 0:
            indent = 2
        try:
            data = json.loads(json_str)
            return json.dumps(data, indent=indent)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"


register(JsonPrettyPrintTool())
