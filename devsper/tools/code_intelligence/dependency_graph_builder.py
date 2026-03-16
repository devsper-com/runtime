"""Build a dependency graph from Python files: module -> imported modules."""

import ast
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DependencyGraphBuilderTool(Tool):
    """
    Build a module-level dependency graph: for each .py file, list its imports (internal or external).
    """

    name = "dependency_graph_builder"
    description = "Build a dependency graph from Python files (module -> imports)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path of the codebase"},
            "max_files": {"type": "integer", "description": "Max files to scan (default 150)"},
        },
        "required": ["path"],
    }

    def _imports(self, p: Path) -> list[str]:
        imports = []
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split(".")[0])
        except (SyntaxError, OSError):
            pass
        return list(dict.fromkeys(imports))

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_files = kwargs.get("max_files", 150)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_files, int) or max_files < 1:
            max_files = 150
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        edges = []
        count = 0
        for p in root.rglob("*.py"):
            if count >= max_files:
                break
            if not p.is_file():
                continue
            count += 1
            mod = str(p.relative_to(root)).replace("\\", "/").replace(".py", "").replace("/", ".")
            for imp in self._imports(p):
                edges.append({"from": mod, "to": imp})
        import json

        return json.dumps({"nodes": "inferred from edges", "edges": edges[:300]}, indent=2)


register(DependencyGraphBuilderTool())
