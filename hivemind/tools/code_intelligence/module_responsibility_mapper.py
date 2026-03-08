"""Map module responsibility using docstrings and top-level exports."""

import ast
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ModuleResponsibilityMapperTool(Tool):
    """
    Map each module to a short responsibility summary (docstring or first line).
    """

    name = "module_responsibility_mapper"
    description = "Map modules to responsibility summaries (docstring/first line)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path"},
            "max_modules": {"type": "integer", "description": "Max modules (default 50)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_modules = kwargs.get("max_modules", 50)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_modules, int) or max_modules < 1:
            max_modules = 50
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        results = []
        for p in root.rglob("*.py"):
            if len(results) >= max_modules:
                break
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
                doc = ast.get_docstring(tree) or ""
                first = text.strip().split("\n")[0][:60] if text.strip() else ""
                summary = (doc.split("\n")[0] if doc else first).strip() or "(no summary)"
                results.append({"module": str(p.relative_to(root)).replace("\\", "/"), "responsibility": summary[:200]})
            except (SyntaxError, OSError):
                continue
        import json

        return json.dumps({"modules": results}, indent=2)


register(ModuleResponsibilityMapperTool())
