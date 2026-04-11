"""ParseCodebase tool — extract functions/classes from a repo or file using tree-sitter."""

from __future__ import annotations

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ParseCodebaseTool(Tool):
    """Parse a codebase or file and return structured function/class information.

    Supports Python, JavaScript, TypeScript, Go, Rust, C/C++, Zig, Bash.
    Uses tree-sitter when available, falls back to ast for Python.
    """

    name = "parse_codebase"
    description = (
        "Parse a directory or file and extract functions, classes, and structure. "
        "Returns a structured summary with file paths, function names, parameters, "
        "and complexity. Supports 10+ languages via tree-sitter."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory or file path to parse (absolute or relative to cwd)",
            },
            "format": {
                "type": "string",
                "enum": ["summary", "json"],
                "description": "Output format: 'summary' (human readable) or 'json'. Default: summary",
            },
            "max_files": {
                "type": "integer",
                "description": "Max files to parse (default 500, max 2000)",
            },
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        from devsper.code_intelligence.parser import parse_repository, parse_file, repo_context_for_llm

        raw_path = kwargs.get("path", "")
        fmt = kwargs.get("format", "summary")
        max_files = min(int(kwargs.get("max_files", 500)), 2000)

        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            return json.dumps({"error": f"Path not found: {raw_path}"})

        if path.is_file():
            from devsper.code_intelligence.parser import parse_file
            fns = parse_file(path, path.parent)
            if fmt == "json":
                return json.dumps([
                    {"name": f.name, "file": f.file, "language": f.language,
                     "line_start": f.line_start, "line_end": f.line_end,
                     "params": f.params, "complexity": f.complexity}
                    for f in fns
                ], indent=2)
            lines = [f"{f.name}({', '.join(f.params)})  L{f.line_start}-{f.line_end}" for f in fns]
            return f"{len(fns)} functions in {path.name}:\n" + "\n".join(lines)

        result = parse_repository(path, max_files=max_files)

        if fmt == "json":
            return json.dumps({
                "summary": result.summary(),
                "files_parsed": result.files_parsed,
                "functions": [
                    {"name": f.name, "file": f.file, "language": f.language,
                     "line_start": f.line_start, "line_end": f.line_end,
                     "params": f.params, "complexity": f.complexity}
                    for f in result.functions
                ],
                "errors": result.errors[:10],
            }, indent=2)

        return repo_context_for_llm(result)


register(ParseCodebaseTool())
