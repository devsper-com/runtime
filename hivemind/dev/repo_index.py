"""
Codebase index for dev agents: AST parsing, dependency graph, symbol search.

Reuses patterns from hivemind.tools.code_intelligence; provides a single API
for agents to understand the generated codebase.
"""

import ast
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    """A top-level symbol (function or class) in a file."""

    name: str
    kind: str  # "function" or "class"
    file: str
    line: int


@dataclass
class DependencyEdge:
    """Module A depends on module B (import)."""

    from_module: str
    to_module: str


@dataclass
class RepoIndex:
    """
    Index of a repo: files, symbols, dependencies.
    Built via AST parsing; supports dependency graph and symbol search.
    """

    root: Path
    files: list[str] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    edges: list[DependencyEdge] = field(default_factory=list)
    docstrings: dict[str, str] = field(default_factory=dict)

    def _rel_path(self, p: Path) -> str:
        return str(p.relative_to(self.root)).replace("\\", "/")

    def _imports(self, p: Path) -> list[str]:
        out: list[str] = []
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        out.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        out.append(node.module.split(".")[0])
        except (SyntaxError, OSError):
            pass
        return list(dict.fromkeys(out))

    def _extract_symbols(self, p: Path) -> list[SymbolInfo]:
        syms: list[SymbolInfo] = []
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            doc = ast.get_docstring(tree)
            if doc:
                self.docstrings[self._rel_path(p)] = doc[:500]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.col_offset == 0:
                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        syms.append(
                            SymbolInfo(
                                name=node.name,
                                kind=kind,
                                file=self._rel_path(p),
                                line=node.lineno or 0,
                            )
                        )
        except (SyntaxError, OSError):
            pass
        return syms

    def build(self, max_files: int = 200) -> None:
        """Build index from repo root: parse AST, collect symbols and dependencies."""
        self.files = []
        self.symbols = []
        self.edges = []
        self.docstrings = {}
        count = 0
        for p in self.root.rglob("*.py"):
            if count >= max_files:
                break
            if not p.is_file() or "__pycache__" in p.parts:
                continue
            count += 1
            rel = self._rel_path(p)
            self.files.append(rel)
            mod = rel.replace(".py", "").replace("/", ".")
            for imp in self._imports(p):
                self.edges.append(DependencyEdge(from_module=mod, to_module=imp))
            self.symbols.extend(self._extract_symbols(p))

    def dependency_graph(self) -> dict[str, list[str]]:
        """Return adjacency list: module -> list of imported modules."""
        out: dict[str, list[str]] = {}
        for e in self.edges:
            out.setdefault(e.from_module, []).append(e.to_module)
        return out

    def symbol_search(self, name: str) -> list[SymbolInfo]:
        """Find symbols whose name contains the given string."""
        name_lower = name.lower()
        return [s for s in self.symbols if name_lower in s.name.lower()]

    def file_search(self, substring: str) -> list[str]:
        """Find files whose path contains the given string."""
        sub = substring.lower()
        return [f for f in self.files if sub in f.lower()]

    def summary(self) -> str:
        """Human-readable summary for agents."""
        lines = [
            f"Root: {self.root}",
            f"Files: {len(self.files)}",
            f"Symbols: {len(self.symbols)}",
            f"Dependencies: {len(self.edges)} edges",
            "",
            "Top-level files:",
        ]
        for f in sorted(self.files)[:30]:
            lines.append(f"  {f}")
        lines.append("")
        lines.append("Symbols (sample):")
        for s in self.symbols[:40]:
            lines.append(f"  {s.kind} {s.name} @ {s.file}:{s.line}")
        return "\n".join(lines)
