import pytest
from devsper.compiler.parser import parse
from devsper.compiler.ir import GraphSpec, RawWorkflowDoc


PROSE_INPUT = (
    "Research quantum computing trends. "
    "Synthesize the key findings into clear themes. "
    "Write a final technical report for engineers."
)

TOML_INPUT = """\
title = "Research workflow"
description = "Multi-step research and write"

[[agents]]
id = "researcher"
role = "Research expert who finds information on a topic"
tools = ["web_search"]
model = "slow"
mutation_point = true

[[agents]]
id = "writer"
role = "Technical writer who writes clear reports"
tools = []
model = "mid"
"""

MARKDOWN_INPUT = """\
# Research Workflow

Steps:
- Research quantum computing trends
- Synthesize findings into key themes
- Write final report for engineers
"""


def test_parse_prose_returns_doc_and_spec():
    doc, spec = parse(PROSE_INPUT)
    assert isinstance(doc, RawWorkflowDoc)
    assert isinstance(spec, GraphSpec)
    assert len(spec.nodes) >= 1


def test_parse_prose_infers_linear_edges():
    _, spec = parse(PROSE_INPUT)
    assert len(spec.edges) == len(spec.nodes) - 1


def test_parse_toml_extracts_agents():
    doc, spec = parse(TOML_INPUT)
    assert doc.title == "Research workflow"
    assert len(spec.nodes) == 2
    assert spec.nodes[0].id == "researcher"
    assert spec.nodes[0].tools == ["web_search"]
    assert spec.nodes[0].model_hint == "slow"
    assert spec.nodes[0].is_mutation_point is True
    assert spec.nodes[1].id == "writer"


def test_parse_toml_edges_connect_agents():
    _, spec = parse(TOML_INPUT)
    assert spec.edges[0].src == "researcher"
    assert spec.edges[0].dst == "writer"


def test_parse_markdown_extracts_bullet_steps():
    doc, spec = parse(MARKDOWN_INPUT)
    assert len(spec.nodes) == 3
    roles = [n.role for n in spec.nodes]
    assert any("quantum" in r.lower() for r in roles)
    assert any("synthes" in r.lower() for r in roles)
    assert any("report" in r.lower() for r in roles)


def test_parse_produces_valid_version():
    _, spec = parse(PROSE_INPUT)
    assert len(spec.version) == 8
    assert spec.version.isalnum()


def test_parse_empty_string_does_not_crash():
    _, spec = parse("Build something useful.")
    assert len(spec.nodes) >= 1
