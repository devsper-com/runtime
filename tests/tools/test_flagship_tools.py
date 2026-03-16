"""Unit tests for the five flagship tools."""

import json
import tempfile
from pathlib import Path
from devsper.tools.flagship.docproc_corpus_pipeline import DocprocCorpusPipelineTool
from devsper.tools.flagship.research_graph_builder import ResearchGraphBuilderTool
from devsper.tools.flagship.repository_semantic_map import RepositorySemanticMapTool
from devsper.tools.flagship.swarm_experiment_runner import SwarmExperimentRunnerTool
from devsper.tools.flagship.distributed_document_analysis import DistributedDocumentAnalysisTool
from devsper.tools.registry import get
from devsper.tools.tool_runner import run_tool


def test_docproc_corpus_pipeline_missing_directory():
    out = run_tool("docproc_corpus_pipeline", {})
    assert "Error" in out or "required" in out.lower()


def test_docproc_corpus_pipeline_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        out = DocprocCorpusPipelineTool().run(directory=d)
    data = json.loads(out)
    assert "documents" in data
    assert data["total_files"] == 0


def test_docproc_corpus_pipeline_nonexistent_dir():
    out = DocprocCorpusPipelineTool().run(directory="/nonexistent/dir/xyz")
    assert "Error" in out


def test_research_graph_builder():
    out = ResearchGraphBuilderTool().run(documents=["Machine learning is used. Neural networks are methods. The dataset is MNIST."])
    data = json.loads(out)
    assert "nodes" in data
    assert "edges" in data
    assert "entity_types" in data


def test_research_graph_builder_missing_documents():
    out = run_tool("research_graph_builder", {})
    assert "Error" in out or "Validation" in out or "Missing" in out or "documents" in out


def test_repository_semantic_map():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "foo.py").write_text('"""A module."""\ndef bar(): pass\n')
        out = RepositorySemanticMapTool().run(repo_path=d)
    data = json.loads(out)
    assert "modules" in data
    assert "dependencies" in data
    assert "entrypoints" in data
    assert "architecture_summary" in data


def test_repository_semantic_map_nonexistent():
    out = RepositorySemanticMapTool().run(repo_path="/nonexistent/repo")
    assert "Error" in out


def test_swarm_experiment_runner():
    out = SwarmExperimentRunnerTool().run(parameters={"task": "Run test"}, runs=2)
    data = json.loads(out)
    assert "mean" in data
    assert "std" in data
    assert "best_configuration" in data
    assert data["runs"] == 2


def test_swarm_experiment_runner_registered():
    t = get("swarm_experiment_runner")
    assert t is not None
    assert t.name == "swarm_experiment_runner"


def test_distributed_document_analysis():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "doc.txt"
        p.write_text("Short text.")
        out = DistributedDocumentAnalysisTool().run(documents=[str(p)])
    data = json.loads(out)
    assert "total_documents" in data
    assert "summaries" in data
    assert "insights" in data


def test_distributed_document_analysis_missing_documents():
    out = run_tool("distributed_document_analysis", {})
    assert "Error" in out or "Validation" in out or "Missing" in out or "documents" in out


def test_all_five_flagship_tools_registered():
    from devsper.tools.registry import list_tools
    names = {t.name for t in list_tools()}
    for name in [
        "docproc_corpus_pipeline",
        "research_graph_builder",
        "repository_semantic_map",
        "swarm_experiment_runner",
        "distributed_document_analysis",
    ]:
        assert name in names, f"Tool {name} should be registered"
