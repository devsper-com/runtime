import pytest
from devsper.compiler import parse, compress, optimize, compile_graph, GEPAConfig


WORKFLOW = """
# Research Workflow

Steps:
- Research quantum computing trends and recent breakthroughs
- Synthesize findings into three key thematic areas
- Write a final technical report for a senior engineering audience
"""


def test_full_pipeline_prose_to_compiled_graph():
    # parse
    doc, seed_spec = parse(WORKFLOW)
    assert len(seed_spec.nodes) >= 2

    # compress
    compressed = compress(seed_spec.nodes[0].role, target_ratio=0.7)
    assert isinstance(compressed, str)
    assert len(compressed) > 0

    # optimize
    config = GEPAConfig(population_size=5, max_generations=3, optimize_for="balanced")
    front = optimize(seed_spec, WORKFLOW, config)
    assert len(front) >= 1
    best = front[0]
    assert len(best.nodes) >= 1

    # compile
    compiled = compile_graph(best)
    assert hasattr(compiled, "invoke") or hasattr(compiled, "ainvoke")


def test_full_pipeline_toml():
    toml = """\
title = "Analysis pipeline"

[[agents]]
id = "analyzer"
role = "Analyze the dataset for patterns"
tools = ["python_exec"]
model = "mid"
mutation_point = true

[[agents]]
id = "reporter"
role = "Generate summary report from analysis"
tools = []
model = "fast"
"""
    doc, seed_spec = parse(toml)
    assert doc.title == "Analysis pipeline"
    config = GEPAConfig(population_size=5, max_generations=3)
    front = optimize(seed_spec, toml, config)
    compiled = compile_graph(front[0])
    assert compiled is not None
