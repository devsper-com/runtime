import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.compiler.objectives import (
    score_f1_token_cost,
    score_f2_task_fidelity,
    score_f3_predicted_performance,
)


def make_spec(roles: list[str], tools: list[list[str]] | None = None) -> GraphSpec:
    if tools is None:
        tools = [[] for _ in roles]
    nodes = [NodeSpec(id=f"n{i}", role=r, tools=t) for i, (r, t) in enumerate(zip(roles, tools))]
    edges = [EdgeSpec(src=nodes[i].id, dst=nodes[i + 1].id) for i in range(len(nodes) - 1)]
    return GraphSpec(nodes=nodes, edges=edges)


def test_f1_bounded_zero_to_one():
    spec = make_spec(["short role"])
    score = score_f1_token_cost(spec)
    assert 0.0 <= score <= 1.0


def test_f1_more_tokens_costs_more():
    cheap = make_spec(["x"])
    expensive = make_spec(["x " * 200])
    assert score_f1_token_cost(cheap) < score_f1_token_cost(expensive)


def test_f1_max_clamps_at_one():
    huge_role = "word " * 10_000
    spec = make_spec([huge_role])
    assert score_f1_token_cost(spec) == 1.0


def test_f2_identical_text_near_one():
    spec = make_spec(["research quantum computing"])
    score = score_f2_task_fidelity(spec, "research quantum computing")
    assert score > 0.95


def test_f2_unrelated_text_low():
    spec = make_spec(["bake a chocolate cake"])
    score = score_f2_task_fidelity(spec, "quantum physics research paper")
    assert score < 0.25


def test_f2_bounded_zero_to_one():
    spec = make_spec(["some role"])
    score = score_f2_task_fidelity(spec, "some prompt")
    assert 0.0 <= score <= 1.0


def test_f3_no_history_returns_half():
    spec = make_spec(["researcher"])
    assert score_f3_predicted_performance(spec) == 0.5


def test_f3_none_history_returns_half():
    spec = make_spec(["researcher"])
    assert score_f3_predicted_performance(spec, None) == 0.5


def test_f3_uses_historical_mean():
    spec = make_spec(["researcher", "writer"])
    history = {"researcher": 0.9, "writer": 0.7}
    result = score_f3_predicted_performance(spec, history)
    assert abs(result - 0.8) < 0.001


def test_f3_unknown_role_defaults_to_half():
    spec = make_spec(["unknown role"])
    history = {"researcher": 0.9}
    result = score_f3_predicted_performance(spec, history)
    assert result == 0.5
