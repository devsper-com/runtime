"""Tests for coding tools."""

import pytest

from devsper.tools.coding.run_python import RunPythonTool
from devsper.tools.coding.extract_functions import ExtractFunctionsTool
from devsper.tools.coding.analyze_code_complexity import AnalyzeCodeComplexityTool
from devsper.tools.coding.dependency_analyzer import DependencyAnalyzerTool
from devsper.tools.coding.repo_structure_map import RepoStructureMapTool


def test_run_python():
    out = RunPythonTool().run(code="print(2 + 3)")
    assert "5" in out


def test_extract_functions():
    code = "def foo(a, b):\n    return a + b"
    out = ExtractFunctionsTool().run(code=code)
    assert "foo" in out and "a" in out and "b" in out


def test_analyze_code_complexity():
    code = "def f():\n    if True:\n        return 1"
    out = AnalyzeCodeComplexityTool().run(code=code)
    assert "Lines" in out or "Branches" in out


def test_dependency_analyzer():
    code = "import os\nfrom pathlib import Path"
    out = DependencyAnalyzerTool().run(code=code)
    assert "os" in out and "pathlib" in out


def test_repo_structure_map(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b.txt").write_text("")
    out = RepoStructureMapTool().run(path=str(tmp_path), max_depth=2)
    assert "a" in out or "b.txt" in out
