"""
Tool runner: execute a tool by name with validated arguments and safe error handling.
"""

import time

from hivemind.tools.registry import get


def _validate_args(args: dict, schema: dict) -> str | None:
    """
    Validate args against JSON Schema-style input_schema.
    Returns None if valid, or an error message string if invalid.
    """
    if not isinstance(args, dict):
        return "args must be a dict"
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for key in required:
        if key not in args:
            return f"Missing required argument: {key}"
    for key, value in args.items():
        if key not in properties:
            continue
        prop = properties[key]
        expected_type = prop.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return f"Argument '{key}' must be a string"
        if expected_type == "number" and not isinstance(value, (int, float)):
            return f"Argument '{key}' must be a number"
        if expected_type == "integer" and not isinstance(value, int):
            return f"Argument '{key}' must be an integer"
        if expected_type == "boolean" and not isinstance(value, bool):
            return f"Argument '{key}' must be a boolean"
        if expected_type == "array" and not isinstance(value, list):
            return f"Argument '{key}' must be an array"
        if expected_type == "object" and not isinstance(value, dict):
            return f"Argument '{key}' must be an object"
    return None


def run_tool(name: str, args: dict) -> str:
    """
    Execute the tool by name with the given arguments.

    Validates args against the tool's input_schema, runs the tool, and returns
    its string output. On validation failure or exception, returns a formatted error string.
    Records usage to tool analytics when available.
    """
    start = time.perf_counter()
    tool = get(name)
    if tool is None:
        _record_analytics(name, False, start)
        return f"Tool not found: {name}"
    err = _validate_args(args, tool.input_schema)
    if err is not None:
        _record_analytics(name, False, start)
        return f"Validation error: {err}"
    try:
        result = tool.run(**args)
        success = not (isinstance(result, str) and result.startswith("Tool error:"))
        _record_analytics(name, success, start)
        return result
    except Exception as e:
        _record_analytics(name, False, start)
        return f"Tool error: {type(e).__name__}: {e}"


def _record_analytics(tool_name: str, success: bool, start_time: float) -> None:
    """Record tool invocation to analytics if available."""
    try:
        from hivemind.analytics import get_default_analytics

        latency_ms = (time.perf_counter() - start_time) * 1000
        get_default_analytics().record(tool_name, success, latency_ms)
    except Exception:
        pass
