"""Tests for the evals harness and prompt optimizer."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from devsper.evals.dataset import EvalDataset
from devsper.evals.metrics import (
    BUILTIN_METRICS,
    contains,
    exact_match,
    get_metric,
    non_empty,
    word_overlap,
)
from devsper.evals.runner import EvalRunner
from devsper.evals.types import EvalCase, EvalResult, EvalSummary
from devsper.prompt_optimizer import (
    OptimizeRequest,
    get_prompt_optimizer,
    reset_prompt_optimizer,
)
from devsper.prompt_optimizer.backends.noop import NoopBackend


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def make_case(expected: str, role: str = "general") -> EvalCase:
    return EvalCase(id="t1", task="test task", expected=expected, role=role)


def test_exact_match_hit():
    c = make_case("hello world")
    assert exact_match(c, "hello world") == 1.0


def test_exact_match_miss():
    c = make_case("hello world")
    assert exact_match(c, "hello") == 0.0


def test_contains_case_insensitive():
    c = make_case("attention")
    assert contains(c, "The Attention Mechanism is key") == 1.0


def test_contains_miss():
    c = make_case("attention")
    assert contains(c, "nothing relevant here") == 0.0


def test_word_overlap_partial():
    c = make_case("quick brown fox")
    score = word_overlap(c, "the quick brown dog")
    assert 0.0 < score < 1.0


def test_non_empty_pass():
    c = make_case("")
    assert non_empty(c, "something") == 1.0


def test_non_empty_fail():
    c = make_case("")
    assert non_empty(c, "  ") == 0.0


def test_get_metric_builtin():
    m = get_metric("contains")
    assert m is contains


def test_get_metric_unknown_raises():
    with pytest.raises(ValueError, match="Unknown metric"):
        get_metric("unknown_metric_xyz")


def test_all_builtin_metrics_present():
    expected = {"exact_match", "contains", "regex_match", "non_empty", "word_overlap"}
    assert expected <= set(BUILTIN_METRICS.keys())


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


def test_dataset_stub_length():
    ds = EvalDataset.stub("research", n=3)
    assert len(ds) == 3


def test_dataset_save_load(tmp_path):
    ds = EvalDataset.stub("code", n=4)
    path = tmp_path / "test.jsonl"
    ds.save(path)
    loaded = EvalDataset.load(path)
    assert len(loaded) == 4
    assert loaded.cases[0].role == "code"


def test_dataset_filter_by_role():
    cases = [
        EvalCase(id="1", task="t1", expected="e1", role="research"),
        EvalCase(id="2", task="t2", expected="e2", role="code"),
        EvalCase(id="3", task="t3", expected="e3", role="research"),
    ]
    ds = EvalDataset(cases)
    filtered = ds.filter_by_role("research")
    assert len(filtered) == 2


def test_dataset_from_dicts():
    records = [{"task": "t", "expected": "e", "role": "general"}]
    ds = EvalDataset.from_dicts(records)
    assert len(ds) == 1
    assert ds.cases[0].id == "0"


# ---------------------------------------------------------------------------
# EvalSummary
# ---------------------------------------------------------------------------


def test_eval_summary_pass_rate():
    cases = [EvalCase(id=str(i), task="t", expected="e") for i in range(4)]
    results = [
        EvalResult(case=cases[0], actual="e", score=1.0, passed=True),
        EvalResult(case=cases[1], actual="", score=0.0, passed=False),
        EvalResult(case=cases[2], actual="e", score=1.0, passed=True),
        EvalResult(case=cases[3], actual="", score=0.0, passed=False),
    ]
    summary = EvalSummary(results=results, metric_name="exact_match", role="general")
    assert summary.pass_rate == 0.5
    assert summary.mean_score == 0.5
    assert summary.passed == 2


def test_eval_summary_as_examples():
    cases = [EvalCase(id=str(i), task=f"task{i}", expected=f"exp{i}") for i in range(3)]
    results = [
        EvalResult(case=cases[0], actual="out0", score=1.0, passed=True),
        EvalResult(case=cases[1], actual="out1", score=0.0, passed=False),
        EvalResult(case=cases[2], actual="out2", score=1.0, passed=True),
    ]
    summary = EvalSummary(results=results, metric_name="x", role="general")
    examples = summary.as_examples()
    assert len(examples) == 2
    assert examples[0] == ("task0", "out0")


# ---------------------------------------------------------------------------
# EvalRunner (mocked agent)
# ---------------------------------------------------------------------------


class _MockAgent:
    model_name = "mock"

    def run(self, task):
        # Returns a mock response where result contains the task description
        class R:
            result = f"Answer for: {task.description}"
        return R()


def test_eval_runner_sync():
    cases = [
        EvalCase(id="1", task="What is AI?", expected="Answer", role="general"),
        EvalCase(id="2", task="Explain ML", expected="Answer", role="general"),
    ]
    ds = EvalDataset(cases)
    runner = EvalRunner(agent=_MockAgent(), metric=contains, pass_threshold=0.5)
    summary = runner.run(ds)
    assert summary.total == 2
    # "Answer" is in "Answer for: ..." so both should pass
    assert summary.passed == 2


def test_eval_runner_role_filter():
    cases = [
        EvalCase(id="1", task="task1", expected="Answer", role="research"),
        EvalCase(id="2", task="task2", expected="Answer", role="code"),
    ]
    ds = EvalDataset(cases)
    runner = EvalRunner(agent=_MockAgent(), metric=contains, pass_threshold=0.5)
    summary = runner.run(ds, role="research")
    assert summary.total == 1
    assert summary.role == "research"


def test_eval_runner_handles_agent_error():
    class _FailAgent:
        model_name = "mock"
        def run(self, task):
            raise RuntimeError("agent exploded")

    cases = [EvalCase(id="1", task="task", expected="x")]
    ds = EvalDataset(cases)
    runner = EvalRunner(agent=_FailAgent(), metric=contains, pass_threshold=0.5)
    summary = runner.run(ds)
    assert summary.results[0].error is not None
    assert summary.results[0].passed is False


# ---------------------------------------------------------------------------
# Prompt optimizer — noop backend
# ---------------------------------------------------------------------------


def test_noop_backend_returns_base_prompt():
    backend = NoopBackend()
    req = OptimizeRequest(
        base_prompt="You are a research specialist.",
        examples=[("task", "output")],
        role="research",
    )
    result = asyncio.run(backend.optimize(req))
    assert result.optimized_prompt == req.base_prompt
    assert result.backend == "noop"


def test_noop_backend_health():
    backend = NoopBackend()
    assert asyncio.run(backend.health()) is True


def test_factory_default_is_noop():
    reset_prompt_optimizer()
    import os
    os.environ.pop("DEVSPER_PROMPT_OPTIMIZER", None)
    opt = get_prompt_optimizer()
    assert opt.name == "noop"
    reset_prompt_optimizer()


def test_factory_env_override(monkeypatch):
    reset_prompt_optimizer()
    monkeypatch.setenv("DEVSPER_PROMPT_OPTIMIZER", "noop")
    opt = get_prompt_optimizer()
    assert opt.name == "noop"
    reset_prompt_optimizer()


def test_factory_config_override():
    from devsper.config.schema import devsperConfigModel, PromptOptimizerConfig

    reset_prompt_optimizer()
    import os
    os.environ.pop("DEVSPER_PROMPT_OPTIMIZER", None)
    cfg = devsperConfigModel()
    cfg.prompt_optimizer = PromptOptimizerConfig(provider="noop")
    opt = get_prompt_optimizer(cfg)
    assert opt.name == "noop"
    reset_prompt_optimizer()


# ---------------------------------------------------------------------------
# roles.py — optimized prompt loading
# ---------------------------------------------------------------------------


def test_get_role_config_falls_back_without_file():
    from devsper.agents.roles import get_role_config

    rc = get_role_config("research_agent")
    assert "research" in rc.prompt_prefix.lower()


def test_get_role_config_loads_optimized_prompt(tmp_path, monkeypatch):
    from devsper.agents.roles import get_role_config

    # Write an optimized prompt file
    opt_dir = tmp_path / ".devsper" / "optimized_prompts"
    opt_dir.mkdir(parents=True)
    (opt_dir / "research_agent.json").write_text(
        json.dumps({"role": "research_agent", "prompt_prefix": "OPTIMIZED PROMPT"})
    )
    # Patch Path to look in tmp_path
    monkeypatch.chdir(tmp_path)
    rc = get_role_config("research_agent")
    assert rc.prompt_prefix == "OPTIMIZED PROMPT"
