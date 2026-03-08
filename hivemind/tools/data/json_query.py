"""Query JSON with a simple key path (e.g. "a.b.0")."""

import json

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class JsonQueryTool(Tool):
    """Get a value from JSON by key path. Path uses dot notation and index for arrays (e.g. data.items.0)."""

    name = "json_query"
    description = "Query JSON with a dot-path (e.g. key.nested.0). Returns the value as string."
    input_schema = {
        "type": "object",
        "properties": {
            "json_str": {"type": "string", "description": "JSON string"},
            "path": {"type": "string", "description": "Dot-separated path, use numbers for list index"},
        },
        "required": ["json_str", "path"],
    }

    def run(self, **kwargs) -> str:
        json_str = kwargs.get("json_str")
        path = kwargs.get("path")
        if json_str is None:
            return "Error: json_str is required"
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        parts = path.strip().split(".")
        try:
            for p in parts:
                if p.isdigit():
                    data = data[int(p)]
                else:
                    data = data[p]
            return json.dumps(data) if not isinstance(data, str) else data
        except (KeyError, IndexError, TypeError) as e:
            return f"Path error: {e}"


register(JsonQueryTool())
