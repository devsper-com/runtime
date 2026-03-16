"""Tests for repo index (devsper.dev.repo_index)."""

import tempfile
from pathlib import Path

import pytest

from devsper.dev.repo_index import RepoIndex, SymbolInfo, DependencyEdge


def test_repo_index_build():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text("def foo(): pass\nclass Bar: pass\n")
        (root / "b.py").write_text("from a import foo\n")
        idx = RepoIndex(root=root)
        idx.build(max_files=10)
        assert len(idx.files) >= 2
        assert any("a.py" in f for f in idx.files)
        syms = idx.symbol_search("foo")
        assert len(syms) >= 1
        assert syms[0].kind == "function"
        deps = idx.dependency_graph()
        assert any("a" in k or "b" in k for k in deps)
        summary = idx.summary()
        assert "Root:" in summary
        assert "Files:" in summary
