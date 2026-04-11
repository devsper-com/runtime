"""CodeMetrics tool — LOC, complexity, and language breakdown for a codebase."""

from __future__ import annotations

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CodeMetricsTool(Tool):
    """Compute code quality metrics for a file or repository.

    Returns line counts (code/comment/blank), function counts, class counts,
    cyclomatic complexity (Python), and language distribution.
    """

    name = "code_metrics"
    description = (
        "Compute code quality metrics: lines of code, comment ratio, function/class counts, "
        "cyclomatic complexity (Python), and language breakdown."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File or directory to analyze",
            },
            "format": {
                "type": "string",
                "enum": ["summary", "json"],
                "description": "Output format. Default: summary",
            },
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        from devsper.code_intelligence.metrics import analyze_file, analyze_repository

        raw_path = kwargs.get("path", "")
        fmt = kwargs.get("format", "summary")

        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            return json.dumps({"error": f"Path not found: {raw_path}"})

        if path.is_file():
            fm = analyze_file(path, path.parent)
            if fm is None:
                return f"Unsupported file type: {path.suffix}"
            if fmt == "json":
                return json.dumps(fm.__dict__, indent=2)
            return (
                f"{fm.path}\n"
                f"  Language: {fm.language}\n"
                f"  Lines: {fm.total_lines} total ({fm.code_lines} code, "
                f"{fm.comment_lines} comment, {fm.blank_lines} blank)\n"
                f"  Functions: {fm.functions} | Classes: {fm.classes}\n"
                f"  Avg complexity: {fm.avg_complexity:.1f} | Max: {fm.max_complexity}"
            )

        rm = analyze_repository(path)
        if fmt == "json":
            return json.dumps({
                "total_files": rm.total_files,
                "total_lines": rm.total_lines,
                "code_lines": rm.code_lines,
                "comment_lines": rm.comment_lines,
                "blank_lines": rm.blank_lines,
                "total_functions": rm.total_functions,
                "total_classes": rm.total_classes,
                "languages": rm.languages,
                "avg_complexity": round(rm.avg_complexity, 2),
                "max_complexity": rm.max_complexity,
            }, indent=2)

        return rm.summary()


register(CodeMetricsTool())
