"""Map directory structure (files and folders) under a path."""

from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RepoStructureMapTool(Tool):
    """List directory tree structure (files and dirs) under a given path."""

    name = "repo_structure_map"
    description = "Map repo/directory structure. Returns indented list of files and dirs."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path to map"},
            "max_depth": {"type": "integer", "description": "Max depth (default 4)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_depth = kwargs.get("max_depth", 4)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_depth, int) or max_depth < 1:
            max_depth = 4
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        lines = []

        def walk(p: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return
            for i, e in enumerate(entries):
                is_last = i == len(entries) - 1
                branch = "└── " if is_last else "├── "
                lines.append(prefix + branch + e.name)
                if e.is_dir():
                    ext = "    " if is_last else "│   "
                    walk(e, prefix + ext, depth + 1)
        lines.append(root.name + "/")
        walk(root, "", 1)
        return "\n".join(lines)


register(RepoStructureMapTool())
