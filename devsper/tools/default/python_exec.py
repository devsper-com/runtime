from __future__ import annotations

import contextlib
import io
import traceback

from devsper.tools.base import Tool
from devsper.tools.registry import register


class PythonExecTool(Tool):
    name = "python_exec"
    description = "Execute Python code in a constrained local context and return stdout."
    category = "coding"
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    }

    def run(self, **kwargs) -> str:
        code = str(kwargs.get("code") or "")
        if not code.strip():
            return "Error: code is required."
        buf = io.StringIO()
        env = {"__name__": "__devsper_tool_exec__"}
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, env, env)  # noqa: S102 - deliberate tool behavior
        except Exception:
            return f"Error: python_exec failed:\n{traceback.format_exc()}"
        out = buf.getvalue().strip()
        return out or "(no output)"


register(PythonExecTool())

