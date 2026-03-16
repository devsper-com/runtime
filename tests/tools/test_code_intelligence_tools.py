"""Tests for code intelligence tools."""

import json
import tempfile
from pathlib import Path

import pytest

from devsper.tools.code_intelligence.codebase_indexer import CodebaseIndexerTool
from devsper.tools.code_intelligence.repository_semantic_index import RepositorySemanticIndexTool
from devsper.tools.code_intelligence.dependency_graph_builder import DependencyGraphBuilderTool
from devsper.tools.code_intelligence.architecture_analyzer import ArchitectureAnalyzerTool
from devsper.tools.code_intelligence.api_surface_extractor import ApiSurfaceExtractorTool
from devsper.tools.code_intelligence.test_coverage_estimator import TestCoverageEstimatorTool
from devsper.tools.code_intelligence.module_responsibility_mapper import ModuleResponsibilityMapperTool
from devsper.tools.code_intelligence.design_pattern_detector import DesignPatternDetectorTool
from devsper.tools.code_intelligence.refactor_candidate_detector import RefactorCandidateDetectorTool
from devsper.tools.code_intelligence.large_function_detector import LargeFunctionDetectorTool
from devsper.tools.code_intelligence.parallel_codebase_analysis import ParallelCodebaseAnalysisTool


def test_codebase_indexer(tmp_path):
    (tmp_path / "foo.py").write_text("def bar(): pass\nclass Baz: pass")
    out = CodebaseIndexerTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "index" in data
    assert any("foo" in str(e.get("file", "")) for e in data["index"])


def test_codebase_indexer_invalid_path():
    out = CodebaseIndexerTool().run(path="/nonexistent/dir")
    assert "Error" in out


def test_repository_semantic_index(tmp_path):
    (tmp_path / "m.py").write_text('"""Module doc."""\npass')
    out = RepositorySemanticIndexTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "entries" in data


def test_dependency_graph_builder(tmp_path):
    (tmp_path / "a.py").write_text("import os\nfrom pathlib import Path")
    out = DependencyGraphBuilderTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "edges" in data


def test_architecture_analyzer(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    out = ArchitectureAnalyzerTool().run(path=str(tmp_path))
    assert "src" in out or "Architecture" in out


def test_api_surface_extractor(tmp_path):
    (tmp_path / "api.py").write_text("def public_fn(x): pass\nclass PublicClass: pass")
    out = ApiSurfaceExtractorTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "api" in data
    assert any("public" in str(s.get("signature", "")) for s in data["api"])


def test_test_coverage_estimator(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test_x(): pass")
    (tmp_path / "src.py").write_text("def f(): pass")
    out = TestCoverageEstimatorTool().run(path=str(tmp_path))
    assert "Source" in out and "Test" in out


def test_module_responsibility_mapper(tmp_path):
    (tmp_path / "m.py").write_text('"""Do something."""\npass')
    out = ModuleResponsibilityMapperTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "modules" in data


def test_design_pattern_detector(tmp_path):
    (tmp_path / "ctx.py").write_text("class C:\n  def __enter__(self): pass\n  def __exit__(self,*a): pass")
    out = DesignPatternDetectorTool().run(path=str(tmp_path))
    data = json.loads(out)
    assert "patterns" in data


def test_refactor_candidate_detector(tmp_path):
    long_fn = "def long_f():\n" + "  x = 1\n" * 40
    (tmp_path / "f.py").write_text(long_fn)
    out = RefactorCandidateDetectorTool().run(path=str(tmp_path), min_lines=30)
    data = json.loads(out)
    assert "candidates" in data


def test_large_function_detector(tmp_path):
    long_fn = "def big():\n" + "  pass\n" * 60
    (tmp_path / "f.py").write_text(long_fn)
    out = LargeFunctionDetectorTool().run(path=str(tmp_path), min_lines=50)
    data = json.loads(out)
    assert "large_functions" in data


def test_parallel_codebase_analysis(tmp_path):
    (tmp_path / "a.py").write_text("pass")
    (tmp_path / "b.py").write_text("pass")
    out = ParallelCodebaseAnalysisTool().run(path=str(tmp_path), batch_size=1)
    data = json.loads(out)
    assert data["total_files"] == 2
    assert data["num_batches"] == 2
