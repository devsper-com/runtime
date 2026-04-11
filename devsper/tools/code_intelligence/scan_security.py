"""ScanSecurity tool — detect common security vulnerabilities via regex patterns."""

from __future__ import annotations

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ScanSecurityTool(Tool):
    """Scan a file or directory for common security vulnerabilities.

    Detects: SQL injection, command injection, hardcoded secrets, weak crypto,
    XSS, path traversal, and insecure deserialization.
    Works on Python, JS/TS, Go, Rust, C/C++, and more.
    """

    name = "scan_security"
    description = (
        "Scan source code for security vulnerabilities (SQL injection, hardcoded secrets, "
        "command injection, XSS, weak crypto, path traversal). Works on files or directories."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File or directory path to scan",
            },
            "format": {
                "type": "string",
                "enum": ["report", "json"],
                "description": "Output format. Default: report",
            },
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        from devsper.code_intelligence.security import (
            scan_file, scan_directory, format_report
        )

        raw_path = kwargs.get("path", "")
        fmt = kwargs.get("format", "report")

        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            return json.dumps({"error": f"Path not found: {raw_path}"})

        if path.is_file():
            issues = scan_file(path, path.parent)
        else:
            issues = scan_directory(path)

        if fmt == "json":
            return json.dumps([
                {"file": i.file, "line": i.line, "severity": i.severity,
                 "category": i.category, "message": i.message, "snippet": i.snippet}
                for i in issues
            ], indent=2)

        return format_report(issues)


register(ScanSecurityTool())
