"""
Security vulnerability scanner — pure regex, no external deps.

Ported from animus/app/services/security.py with all DB/service deps removed.
Works on local file paths directly.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "env", "target", "dist", "build"}

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go",
    ".c", ".cpp", ".cc", ".h", ".hpp", ".rb", ".php",
}


@dataclass
class SecurityIssue:
    file: str
    line: int
    severity: str       # "error" | "warning"
    category: str       # e.g. "sql_injection"
    message: str
    snippet: str


VULNERABILITY_PATTERNS: dict[str, list[tuple[str, str, str]]] = {
    "sql_injection": [
        (r"execute\s*\(\s*['\"].*%.*['\"]",        "error",   "SQL injection: string formatting in SQL query"),
        (r"\.format\s*\(.*SELECT",                  "error",   "SQL injection: .format() in SQL query"),
        (r"f['\"].*SELECT.*\{.*\}.*['\"]",          "error",   "SQL injection: f-string in SQL query"),
        (r"cursor\.execute\s*\(\s*\w+\s*\+",        "error",   "SQL injection: string concatenation in execute()"),
    ],
    "command_injection": [
        (r"\bos\.system\s*\(",                      "error",   "Command injection: os.system() usage"),
        (r"subprocess\.(call|run|Popen)\s*\(.*shell\s*=\s*True", "error", "Command injection: shell=True in subprocess"),
        (r"\beval\s*\(",                             "error",   "Code injection: eval() usage"),
        (r"\bexec\s*\(",                             "warning", "Code injection: exec() usage"),
    ],
    "hardcoded_secrets": [
        (r"(?i)password\s*=\s*['\"][^'\"]{4,}['\"]",  "error",   "Hardcoded password"),
        (r"(?i)api_key\s*=\s*['\"][^'\"]{8,}['\"]",   "error",   "Hardcoded API key"),
        (r"(?i)secret\s*=\s*['\"][^'\"]{8,}['\"]",    "error",   "Hardcoded secret"),
        (r"(?i)token\s*=\s*['\"][^'\"]{8,}['\"]",     "error",   "Hardcoded token"),
        (r"(?i)private_key\s*=\s*['\"][^'\"]{8,}['\"]","error",  "Hardcoded private key"),
    ],
    "weak_crypto": [
        (r"hashlib\.md5\s*\(",                      "warning", "Weak hash: MD5"),
        (r"hashlib\.sha1\s*\(",                     "warning", "Weak hash: SHA1"),
        (r"\bDES\s*\(",                             "error",   "Weak encryption: DES"),
        (r"AES.ECB",                                "warning", "Weak cipher mode: AES-ECB"),
    ],
    "xss": [
        (r"innerHTML\s*=",                          "error",   "XSS: innerHTML assignment"),
        (r"dangerouslySetInnerHTML",                "warning", "XSS: React dangerouslySetInnerHTML"),
        (r"document\.write\s*\(",                   "error",   "XSS: document.write()"),
        (r"\.html\s*\(\s*[^'\"]",                   "warning", "XSS: jQuery .html() with variable"),
    ],
    "path_traversal": [
        (r"open\s*\(.*\.\./",                       "error",   "Path traversal: ../ in open()"),
        (r"\.\./.*\.\./",                           "error",   "Path traversal: multiple ../ sequences"),
    ],
    "insecure_deserialization": [
        (r"\bpickle\.loads?\s*\(",                  "error",   "Insecure deserialization: pickle"),
        (r"\byaml\.load\s*\([^,)]+\)",              "warning", "Insecure deserialization: yaml.load without Loader"),
        (r"\beval\s*\(.*json",                      "error",   "Insecure deserialization: eval on JSON"),
    ],
}


def scan_file(path: Path, root: Optional[Path] = None) -> list[SecurityIssue]:
    """Scan a single file for security issues. Returns list of SecurityIssue."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rel = str(path.relative_to(root)) if root else str(path)
    lines = content.splitlines()
    issues: list[SecurityIssue] = []

    for category, patterns in VULNERABILITY_PATTERNS.items():
        for pattern, severity, message in patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            for lineno, line in enumerate(lines, 1):
                if compiled.search(line):
                    issues.append(SecurityIssue(
                        file=rel,
                        line=lineno,
                        severity=severity,
                        category=category,
                        message=message,
                        snippet=line.strip()[:120],
                    ))

    return issues


def scan_directory(root: Path, extensions: set[str] | None = None) -> list[SecurityIssue]:
    """Recursively scan a directory. Returns all security issues found."""
    exts = extensions or CODE_EXTENSIONS
    all_issues: list[SecurityIssue] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in exts:
            continue
        all_issues.extend(scan_file(path, root))

    return all_issues


def format_report(issues: list[SecurityIssue], max_items: int = 50) -> str:
    """Format issues as a readable text report."""
    if not issues:
        return "No security issues found."

    by_severity: dict[str, list[SecurityIssue]] = {}
    for issue in issues:
        by_severity.setdefault(issue.severity, []).append(issue)

    lines = [f"Security scan: {len(issues)} issue(s) found\n"]

    for severity in ("error", "warning"):
        bucket = by_severity.get(severity, [])
        if not bucket:
            continue
        lines.append(f"## {severity.upper()} ({len(bucket)})")
        for issue in bucket[:max_items]:
            lines.append(f"  {issue.file}:{issue.line}  [{issue.category}]  {issue.message}")
            lines.append(f"    > {issue.snippet}")
        if len(bucket) > max_items:
            lines.append(f"  ... and {len(bucket) - max_items} more")
        lines.append("")

    return "\n".join(lines)
