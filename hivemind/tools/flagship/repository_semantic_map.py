"""Generate a semantic architecture map of a codebase: modules, dependencies, entrypoints, summary."""

import ast
import json
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class RepositorySemanticMapTool(Tool):
    """
    Generate a semantic architecture map of a codebase: scan files, parse AST,
    extract modules, build dependency graph, summarize responsibilities.
    Output: modules, dependencies, entrypoints, architecture_summary.
    """

    name = "repository_semantic_map"
    description = "Generate a semantic architecture map of a codebase: modules, dependencies, entrypoints, architecture_summary."
    input_schema = {
        "type": "object",
        "properties": {"repo_path": {"type": "string", "description": "Path to repository root"}},
        "required": ["repo_path"],
    }

    def _imports(self, p: Path, root: Path) -> list[str]:
        rel = str(p.relative_to(root)).replace("\\", "/").replace(".py", "").replace("/", ".")
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

    def _responsibility(self, p: Path) -> str:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            doc = ast.get_docstring(tree)
            if doc:
                return doc.split("\n")[0][:120].strip()
            first = p.read_text(encoding="utf-8", errors="replace").strip().split("\n")
            for line in first[:5]:
                if line.strip().startswith("class ") or line.strip().startswith("def "):
                    return line.strip()[:80]
        except (SyntaxError, OSError):
            pass
        return ""

    def run(self, **kwargs) -> str:
        repo_path = kwargs.get("repo_path")
        if not repo_path or not isinstance(repo_path, str):
            return "Error: repo_path must be a non-empty string"
        root = Path(repo_path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: repo_path not found: {repo_path}"

        modules = []
        dependencies = []
        entrypoints = []
        max_files = 150

        py_files = list(root.rglob("*.py"))
        for p in py_files[:max_files]:
            if not p.is_file():
                continue
            rel = str(p.relative_to(root)).replace("\\", "/")
            mod = rel.replace(".py", "").replace("/", ".")
            if "__pycache__" in mod or mod.startswith("."):
                continue
            resp = self._responsibility(p)
            modules.append({"module": mod, "file": rel, "responsibility": resp})
            for imp in self._imports(p, root):
                if imp and imp != mod.split(".")[0]:
                    dependencies.append({"from": mod, "to": imp})
            if "main" in p.name or "__main__" in rel or "run" in p.stem.lower():
                entrypoints.append(mod)

        entrypoints = list(dict.fromkeys(entrypoints))[:20]
        architecture_summary = (
            f"Modules: {len(modules)}. Dependencies: {len(dependencies)}. "
            f"Entrypoints: {', '.join(entrypoints[:5]) or 'none detected'}."
        )

        return json.dumps({
            "modules": modules[:80],
            "dependencies": dependencies[:200],
            "entrypoints": entrypoints,
            "architecture_summary": architecture_summary,
        }, indent=2)


register(RepositorySemanticMapTool())
