"""
Code quality metrics — pure Python, no external deps.

Computes LOC, comment ratio, complexity distribution, and per-file summaries.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
             "env", "target", "dist", "build"}


@dataclass
class FileMetrics:
    path: str
    language: str
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    functions: int = 0
    classes: int = 0
    avg_complexity: float = 0.0
    max_complexity: int = 0


@dataclass
class RepoMetrics:
    total_files: int = 0
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0
    languages: dict[str, int] = field(default_factory=dict)   # lang → file count
    avg_complexity: float = 0.0
    max_complexity: int = 0
    files: list[FileMetrics] = field(default_factory=list)

    def summary(self) -> str:
        lang_str = ", ".join(f"{l}: {n}" for l, n in sorted(self.languages.items()))
        return (
            f"{self.total_files} files | "
            f"{self.total_lines:,} lines ({self.code_lines:,} code) | "
            f"{self.total_functions} functions | {self.total_classes} classes\n"
            f"Languages: {lang_str or 'unknown'}\n"
            f"Avg complexity: {self.avg_complexity:.1f} | Max: {self.max_complexity}"
        )


# Extension → language name
_EXT_LANG = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp",
    ".cc": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".java": "java",
    ".sh": "bash", ".bash": "bash",
}


def _count_lines(content: str, lang: str) -> tuple[int, int, int]:
    """Returns (code_lines, comment_lines, blank_lines)."""
    lines = content.splitlines()
    code = comment = blank = 0

    # Comment markers per language
    line_comment = {
        "python": "#", "ruby": "#", "bash": "#",
        "javascript": "//", "typescript": "//",
        "go": "//", "rust": "//", "c": "//", "cpp": "//",
        "java": "//", "php": "//",
    }.get(lang, "#")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
        elif stripped.startswith(line_comment):
            comment += 1
        else:
            code += 1

    return code, comment, blank


def _python_complexity(source: str) -> list[int]:
    """Return cyclomatic complexity for each function in Python source."""
    branch_nodes = (ast.If, ast.For, ast.While, ast.ExceptHandler,
                    ast.With, ast.Assert, ast.comprehension)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    complexities: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cx = 1 + sum(1 for _ in ast.walk(node) if isinstance(_, branch_nodes))
            complexities.append(cx)
    return complexities


def analyze_file(path: Path, root: Path | None = None) -> FileMetrics | None:
    ext = path.suffix.lower()
    lang = _EXT_LANG.get(ext)
    if not lang:
        return None

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    rel = str(path.relative_to(root)) if root else str(path)
    code, comment, blank = _count_lines(content, lang)
    total = code + comment + blank

    fm = FileMetrics(
        path=rel,
        language=lang,
        total_lines=total,
        code_lines=code,
        comment_lines=comment,
        blank_lines=blank,
    )

    if lang == "python":
        complexities = _python_complexity(content)
        fm.functions = len(complexities)
        # Count classes roughly
        fm.classes = content.count("\nclass ") + (1 if content.startswith("class ") else 0)
        if complexities:
            fm.avg_complexity = sum(complexities) / len(complexities)
            fm.max_complexity = max(complexities)
    else:
        # Simple heuristics for other languages
        fm.functions = len(re.findall(r"\bfunc\b|\bfunction\b|\bdef\b|\bfn\b", content))
        fm.classes = len(re.findall(r"\bclass\b|\bstruct\b|\binterface\b", content))

    return fm


def analyze_repository(root: Path) -> RepoMetrics:
    """Walk a repo and compute aggregate metrics."""
    rm = RepoMetrics()
    complexities_all: list[float] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        fm = analyze_file(path, root)
        if fm is None:
            continue

        rm.total_files += 1
        rm.total_lines += fm.total_lines
        rm.code_lines += fm.code_lines
        rm.comment_lines += fm.comment_lines
        rm.blank_lines += fm.blank_lines
        rm.total_functions += fm.functions
        rm.total_classes += fm.classes
        rm.languages[fm.language] = rm.languages.get(fm.language, 0) + 1
        if fm.avg_complexity:
            complexities_all.append(fm.avg_complexity)
        if fm.max_complexity > rm.max_complexity:
            rm.max_complexity = fm.max_complexity
        rm.files.append(fm)

    if complexities_all:
        rm.avg_complexity = sum(complexities_all) / len(complexities_all)

    return rm
