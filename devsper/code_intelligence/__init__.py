"""
devsper code intelligence — multi-language parsing, security scanning, code metrics.

Ported from animus and stripped of all microservice/DB dependencies.
Works standalone using tree-sitter (optional) + ast (always available).
"""

from devsper.code_intelligence.parser import (
    ParseResult,
    FunctionInfo,
    parse_file,
    parse_repository,
    repo_context_for_llm,
)
from devsper.code_intelligence.security import (
    SecurityIssue,
    scan_file,
    scan_directory,
    format_report as format_security_report,
)
from devsper.code_intelligence.metrics import (
    FileMetrics,
    RepoMetrics,
    analyze_file,
    analyze_repository,
)

__all__ = [
    "ParseResult", "FunctionInfo", "parse_file", "parse_repository", "repo_context_for_llm",
    "SecurityIssue", "scan_file", "scan_directory", "format_security_report",
    "FileMetrics", "RepoMetrics", "analyze_file", "analyze_repository",
]
