"""Extract the public API surface: non-_ prefixed functions and classes with signatures."""

import ast
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ApiSurfaceExtractorTool(Tool):
    """
    Extract public API: top-level functions and classes that do not start with underscore.
    """

    name = "api_surface_extractor"
    description = "Extract public API surface (non-_ names) with argument lists."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to file or directory"},
            "max_symbols": {"type": "integer", "description": "Max symbols (default 80)"},
        },
        "required": ["path"],
    }

    def _arg_list(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = [a.arg for a in node.args.args if a.arg != "self"]
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        return ", ".join(args)

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_symbols = kwargs.get("max_symbols", 80)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_symbols, int) or max_symbols < 1:
            max_symbols = 80
        p = Path(path).resolve()
        if not p.exists():
            return f"Error: path not found: {path}"
        files = [p] if p.is_file() and p.suffix == ".py" else list(p.rglob("*.py")) if p.is_dir() else []
        symbols = []
        for f in files:
            if not f.is_file():
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
                rel = f.relative_to(p if p.is_dir() else f.parent)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name.startswith("_"):
                            continue
                        kind = "class" if isinstance(node, ast.ClassDef) else "def"
                        if kind == "def":
                            sig = f"{node.name}({self._arg_list(node)})"  # type: ignore[arg-type]
                        else:
                            sig = node.name
                        symbols.append({"file": str(rel), "kind": kind, "signature": sig})
                    if len(symbols) >= max_symbols:
                        break
            except (SyntaxError, OSError):
                continue
            if len(symbols) >= max_symbols:
                break
        import json

        return json.dumps({"api": symbols}, indent=2)


register(ApiSurfaceExtractorTool())
