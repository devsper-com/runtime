"""Analyze codebase architecture: package layout, entry points, and high-level structure."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ArchitectureAnalyzerTool(Tool):
    """
    Report high-level architecture: top-level packages, __main__ and main-like files, and layout.
    """

    name = "architecture_analyzer"
    description = "Analyze codebase architecture: packages, entry points, layout."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path"},
            "max_depth": {"type": "integer", "description": "Max depth for layout (default 3)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_depth = kwargs.get("max_depth", 3)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_depth, int) or max_depth < 1:
            max_depth = 3
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        top_dirs = []
        for d in root.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "__pycache__":
                top_dirs.append(d.name)
        main_files = []
        for p in root.rglob("*.py"):
            if not p.is_file():
                continue
            name = p.name.lower()
            if name in ("__main__.py", "main.py", "run.py", "app.py"):
                main_files.append(str(p.relative_to(root)).replace("\\", "/"))
        layout = []
        for d in sorted(top_dirs)[:20]:
            sub = root / d
            if sub.is_dir():
                py_count = sum(1 for _ in sub.rglob("*.py"))
                layout.append(f"  {d}/ ({py_count} .py files)")
        lines = [
            "Architecture summary",
            "=" * 40,
            "Top-level packages: " + ", ".join(sorted(top_dirs)[:15]),
            "",
            "Entry-point-like files: " + ", ".join(main_files[:10]) or "none found",
            "",
            "Layout (top-level):",
            "\n".join(layout),
        ]
        return "\n".join(lines)


register(ArchitectureAnalyzerTool())
