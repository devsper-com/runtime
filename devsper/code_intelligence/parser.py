"""
Multi-language code parser backed by Tree-sitter (optional) with ast fallback for Python.

Ported and simplified from animus/app/services/parser.py — DB / Qdrant / embedding
layers removed. Works standalone with no external services.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language map
# ---------------------------------------------------------------------------

EXTENSION_LANG: dict[str, str] = {
    "py": "python", "pyw": "python",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "c": "c", "h": "c",
    "cpp": "cpp", "cc": "cpp", "cxx": "cpp", "hpp": "cpp",
    "go": "go",
    "rs": "rust",
    "zig": "zig",
    "sh": "bash", "bash": "bash",
}

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", "env", "dist", "build", ".next",
    "target", ".cargo", "vendor",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FunctionInfo:
    name: str
    file: str               # relative to repo root
    language: str
    line_start: int
    line_end: int
    params: list[str] = field(default_factory=list)
    docstring: str = ""
    complexity: int = 1     # cyclomatic approximation


@dataclass
class ParseResult:
    root: str               # repo root (abs path)
    files_parsed: int = 0
    functions: list[FunctionInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        langs: dict[str, int] = {}
        for fn in self.functions:
            langs[fn.language] = langs.get(fn.language, 0) + 1
        lang_str = ", ".join(f"{l}:{n}" for l, n in sorted(langs.items()))
        return (
            f"{self.files_parsed} files parsed, "
            f"{len(self.functions)} functions found"
            + (f" [{lang_str}]" if lang_str else "")
        )


# ---------------------------------------------------------------------------
# Tree-sitter helpers (optional)
# ---------------------------------------------------------------------------

_TS_PARSERS: dict[str, object] | None = None  # lazy init
_TS_AVAILABLE = False


def _init_ts() -> bool:
    global _TS_PARSERS, _TS_AVAILABLE
    if _TS_PARSERS is not None:
        return _TS_AVAILABLE
    _TS_PARSERS = {}
    try:
        from tree_sitter import Parser  # noqa: F401

        try:
            import pantoufle_tree_sitter_languages as ptsl  # animus's bundled package

            supported = ["python", "javascript", "typescript", "c", "cpp",
                         "go", "rust", "zig", "bash"]
            for lang in supported:
                try:
                    _TS_PARSERS[lang] = (ptsl.get_language(lang), Parser())
                    _TS_PARSERS[lang][1].set_language(_TS_PARSERS[lang][0])
                except Exception:
                    pass
        except ImportError:
            # Fall back to individual tree-sitter-* packages
            _lang_modules = {
                "python": "tree_sitter_python",
                "javascript": "tree_sitter_javascript",
                "typescript": "tree_sitter_typescript",
                "c": "tree_sitter_c",
                "cpp": "tree_sitter_cpp",
                "go": "tree_sitter_go",
                "rust": "tree_sitter_rust",
                "bash": "tree_sitter_bash",
            }
            for lang, mod in _lang_modules.items():
                try:
                    m = __import__(mod)
                    from tree_sitter import Language, Parser
                    language = Language(m.language())
                    parser = Parser()
                    parser.set_language(language)
                    _TS_PARSERS[lang] = (language, parser)
                except Exception:
                    pass

        _TS_AVAILABLE = bool(_TS_PARSERS)
        if _TS_AVAILABLE:
            log.debug("Tree-sitter active for: %s", list(_TS_PARSERS.keys()))
    except ImportError:
        log.debug("tree-sitter not installed, using ast fallback")
    return _TS_AVAILABLE


# ---------------------------------------------------------------------------
# AST-based Python parser (always available)
# ---------------------------------------------------------------------------

def _parse_python_ast(source: str, rel_path: str) -> list[FunctionInfo]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[FunctionInfo] = []

    def _complexity(node: ast.AST) -> int:
        """Rough cyclomatic complexity: count branches."""
        branch_types = (ast.If, ast.For, ast.While, ast.ExceptHandler,
                        ast.With, ast.Assert, ast.comprehension)
        return 1 + sum(1 for _ in ast.walk(node) if isinstance(_, branch_types))

    def _collect(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}" if prefix else child.name
                params = [a.arg for a in child.args.args]
                doc = ast.get_docstring(child) or ""
                results.append(FunctionInfo(
                    name=name,
                    file=rel_path,
                    language="python",
                    line_start=child.lineno,
                    line_end=getattr(child, "end_lineno", child.lineno),
                    params=params,
                    docstring=doc[:200],
                    complexity=_complexity(child),
                ))
                _collect(child, prefix=name + ".")
            elif isinstance(child, ast.ClassDef):
                _collect(child, prefix=child.name + ".")

    _collect(tree)
    return results


# ---------------------------------------------------------------------------
# Tree-sitter based extractors for non-Python languages
# ---------------------------------------------------------------------------

def _ts_query_functions(
    lang_name: str, source_bytes: bytes, rel_path: str
) -> list[FunctionInfo]:
    """Extract functions using tree-sitter node iteration (no query DSL needed)."""
    if not _init_ts() or lang_name not in _TS_PARSERS:  # type: ignore[arg-type]
        return []

    _, parser = _TS_PARSERS[lang_name]  # type: ignore[index]
    tree = parser.parse(source_bytes)

    # Node types that represent function definitions across languages
    FN_TYPES = {
        "javascript": {"function_declaration", "function_expression",
                       "arrow_function", "method_definition"},
        "typescript": {"function_declaration", "function_expression",
                       "arrow_function", "method_definition"},
        "c": {"function_definition"},
        "cpp": {"function_definition"},
        "go": {"function_declaration", "method_declaration"},
        "rust": {"function_item"},
        "zig": {"fn_proto", "fn_decl"},
        "bash": {"function_definition"},
    }

    fn_node_types = FN_TYPES.get(lang_name, set())
    results: list[FunctionInfo] = []
    source_lines = source_bytes.decode("utf-8", errors="replace").splitlines()

    def _visit(node) -> None:
        if node.type in fn_node_types:
            # Try to get name
            name = _ts_get_name(node, lang_name, source_bytes)
            if name:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                results.append(FunctionInfo(
                    name=name,
                    file=rel_path,
                    language=lang_name,
                    line_start=start_line,
                    line_end=end_line,
                    complexity=1,
                ))
        for child in node.children:
            _visit(child)

    _visit(tree.root_node)
    return results


def _ts_get_name(node, lang: str, source_bytes: bytes) -> str:
    """Extract the name from a function node."""
    for child in node.children:
        if child.type == "identifier":
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        if child.type == "property_identifier":
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    # Fallback: look deeper one level
    for child in node.children:
        for grandchild in child.children:
            if grandchild.type in ("identifier", "property_identifier"):
                return source_bytes[grandchild.start_byte:grandchild.end_byte].decode("utf-8", errors="replace")
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_file(path: Path, root: Path) -> list[FunctionInfo]:
    """Parse a single file and return its functions."""
    ext = path.suffix.lstrip(".").lower()
    lang = EXTENSION_LANG.get(ext)
    if not lang:
        return []

    try:
        source = path.read_bytes()
    except OSError:
        return []

    rel = str(path.relative_to(root))

    if lang == "python":
        return _parse_python_ast(source.decode("utf-8", errors="replace"), rel)

    if _init_ts():
        return _ts_query_functions(lang, source, rel)

    return []


def parse_repository(
    root: Path,
    max_files: int = 2000,
    skip_dirs: set[str] | None = None,
) -> ParseResult:
    """Walk a repo and parse all supported source files."""
    skip = (skip_dirs or set()) | SKIP_DIRS
    result = ParseResult(root=str(root))

    source_files: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            if any(part in skip for part in p.parts):
                continue
            ext = p.suffix.lstrip(".").lower()
            if ext in EXTENSION_LANG:
                source_files.append(p)
        if len(source_files) >= max_files:
            break

    for p in source_files:
        try:
            fns = parse_file(p, root)
            result.functions.extend(fns)
            result.files_parsed += 1
        except Exception as exc:
            result.errors.append(f"{p}: {exc}")

    return result


def repo_context_for_llm(result: ParseResult, max_entries: int = 120) -> str:
    """Format a ParseResult into a compact text block suitable for LLM context."""
    lines: list[str] = [result.summary(), ""]

    # Group by file
    by_file: dict[str, list[FunctionInfo]] = {}
    for fn in result.functions:
        by_file.setdefault(fn.file, []).append(fn)

    count = 0
    for fpath, fns in sorted(by_file.items()):
        if count >= max_entries:
            remaining = len(result.functions) - count
            lines.append(f"... and {remaining} more functions in other files")
            break
        lines.append(f"### {fpath}")
        for fn in fns[:15]:
            params = f"({', '.join(fn.params)})" if fn.params else "()"
            cx = f" [complexity={fn.complexity}]" if fn.complexity > 5 else ""
            lines.append(f"  {fn.name}{params} L{fn.line_start}{cx}")
            if fn.docstring:
                short = fn.docstring.split("\n")[0][:80]
                lines.append(f"    # {short}")
            count += 1
        lines.append("")

    return "\n".join(lines)
