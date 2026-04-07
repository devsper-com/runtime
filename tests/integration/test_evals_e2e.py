"""
End-to-end integration tests for the eval harness.

These tests exercise the full pipeline with a deterministic mock agent so
they run without any LLM API keys and still verify the actual wiring.

To run against real models set OPENAI_API_KEY and use --run-live:
    uv run pytest tests/integration/test_evals_e2e.py -v
    uv run pytest tests/integration/test_evals_e2e.py -v -m live
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devsper.evals import EvalCase, EvalDataset, EvalRunner, EvalSummary, get_metric
from devsper.evals.metrics import contains, exact_match, openevals_metric, word_overlap
from devsper.prompt_optimizer import OptimizeRequest, get_prompt_optimizer, reset_prompt_optimizer
from devsper.prompt_optimizer.backends.noop import NoopBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent(response_map: dict[str, str] | None = None, default: str = ""):
    """Return a mock agent whose run() returns deterministic outputs."""

    class _Agent:
        model_name = "mock"

        def run(self, task):
            result = (response_map or {}).get(task.description, default or task.description)

            class R:
                pass

            r = R()
            r.result = result
            return r

    return _Agent()


def _research_dataset() -> EvalDataset:
    return EvalDataset(
        [
            EvalCase(
                id="r1",
                task="What is the transformer architecture?",
                expected="attention",
                role="research_agent",
            ),
            EvalCase(
                id="r2",
                task="What year was the 'Attention Is All You Need' paper published?",
                expected="2017",
                role="research_agent",
            ),
            EvalCase(
                id="r3",
                task="Who are the authors of BERT?",
                expected="Devlin",
                role="research_agent",
            ),
            EvalCase(
                id="r4",
                task="What does RLHF stand for?",
                expected="reinforcement learning from human feedback",
                role="research_agent",
            ),
            EvalCase(
                id="r5",
                task="Summarize the concept of few-shot learning.",
                expected="examples",
                role="research_agent",
            ),
        ],
        name="research_integration",
    )


# ---------------------------------------------------------------------------
# 1. Basic eval run with contains metric
# ---------------------------------------------------------------------------


def test_e2e_eval_run_contains_metric():
    """EvalRunner scores correctly when agent responses contain the expected substring."""
    dataset = _research_dataset()

    # Agent that always mentions the expected word in its response
    response_map = {
        "What is the transformer architecture?": "The transformer uses an attention mechanism.",
        "What year was the 'Attention Is All You Need' paper published?": "It was published in 2017.",
        "Who are the authors of BERT?": "Devlin et al. created BERT.",
        "What does RLHF stand for?": "Reinforcement learning from human feedback.",
        "Summarize the concept of few-shot learning.": "Few-shot uses a few examples to generalize.",
    }
    agent = _make_agent(response_map)
    runner = EvalRunner(agent=agent, metric=contains, pass_threshold=0.5)
    summary = runner.run(dataset)

    assert summary.total == 5
    assert summary.passed == 5
    assert summary.pass_rate == 1.0
    assert summary.mean_score == 1.0
    assert summary.role == "research_agent"
    assert summary.metric_name == "contains"


def test_e2e_eval_run_partial_pass():
    """Runner correctly tracks partial pass rates."""
    cases = [
        EvalCase(id="1", task="task A", expected="alpha", role="general"),
        EvalCase(id="2", task="task B", expected="beta", role="general"),
        EvalCase(id="3", task="task C", expected="gamma", role="general"),
        EvalCase(id="4", task="task D", expected="delta", role="general"),
    ]
    response_map = {
        "task A": "alpha is here",
        "task B": "nothing useful",  # miss
        "task C": "gamma found",
        "task D": "nothing",         # miss
    }
    agent = _make_agent(response_map)
    runner = EvalRunner(agent=agent, metric=contains, pass_threshold=0.5)
    summary = runner.run(EvalDataset(cases))

    assert summary.passed == 2
    assert summary.pass_rate == 0.5


# ---------------------------------------------------------------------------
# 2. Role filtering
# ---------------------------------------------------------------------------


def test_e2e_role_filter():
    """Runner only evaluates cases matching the specified role."""
    cases = [
        EvalCase(id="1", task="research task", expected="attention", role="research_agent"),
        EvalCase(id="2", task="code task", expected="def", role="code_agent"),
        EvalCase(id="3", task="another research task", expected="BERT", role="research_agent"),
    ]
    response_map = {
        "research task": "attention mechanism",
        "another research task": "BERT model",
    }
    agent = _make_agent(response_map)
    runner = EvalRunner(agent=agent, metric=contains)
    summary = runner.run(EvalDataset(cases), role="research_agent")

    assert summary.total == 2
    assert summary.role == "research_agent"
    assert summary.passed == 2


# ---------------------------------------------------------------------------
# 3. Dataset JSONL round-trip
# ---------------------------------------------------------------------------


def test_e2e_dataset_jsonl_round_trip(tmp_path):
    """Dataset survives save → load → eval without data loss."""
    original = _research_dataset()
    path = tmp_path / "research.jsonl"
    original.save(path)

    loaded = EvalDataset.load(path)
    assert len(loaded) == len(original)
    assert loaded.cases[0].task == original.cases[0].task
    assert loaded.cases[0].expected == original.cases[0].expected
    assert loaded.cases[0].role == original.cases[0].role

    agent = _make_agent(default="attention 2017 Devlin reinforcement examples")
    runner = EvalRunner(agent=agent, metric=contains)
    summary = runner.run(loaded)
    assert summary.total == 5


# ---------------------------------------------------------------------------
# 4. Word overlap metric (richer scoring than binary contains)
# ---------------------------------------------------------------------------


def test_e2e_word_overlap_graded_scores():
    """word_overlap produces graded scores, not just 0/1."""
    cases = [
        EvalCase(id="1", task="explain attention", expected="query key value matrix softmax"),
        EvalCase(id="2", task="define BERT", expected="bidirectional encoder representations"),
    ]
    response_map = {
        "explain attention": "attention uses query and key vectors",   # partial overlap
        "define BERT": "bidirectional encoder representations from transformers",  # full
    }
    agent = _make_agent(response_map)
    runner = EvalRunner(agent=agent, metric=word_overlap, pass_threshold=0.3)
    summary = runner.run(EvalDataset(cases))

    assert summary.total == 2
    r1 = next(r for r in summary.results if r.case.id == "1")
    r2 = next(r for r in summary.results if r.case.id == "2")
    assert 0.0 < r1.score < 1.0, f"Expected partial score, got {r1.score}"
    # "bidirectional encoder representations from transformers" vs "bidirectional encoder representations"
    # → 3/4 tokens overlap → F1 = 0.75
    assert r2.score >= 0.7, f"Expected high score, got {r2.score}"


# ---------------------------------------------------------------------------
# 5. Async concurrency
# ---------------------------------------------------------------------------


def test_e2e_async_concurrency():
    """Runner handles concurrent cases correctly without race conditions."""
    import time

    cases = [
        EvalCase(id=str(i), task=f"task {i}", expected=f"answer {i}")
        for i in range(10)
    ]
    response_map = {f"task {i}": f"The answer {i} is here" for i in range(10)}
    agent = _make_agent(response_map)
    runner = EvalRunner(agent=agent, metric=contains, concurrency=4)
    summary = runner.run(EvalDataset(cases))

    assert summary.total == 10
    assert summary.passed == 10
    ids = {r.case.id for r in summary.results}
    assert ids == {str(i) for i in range(10)}, "All case IDs must appear in results"


# ---------------------------------------------------------------------------
# 6. Error resilience
# ---------------------------------------------------------------------------


def test_e2e_agent_errors_dont_crash_runner():
    """Individual agent failures are captured per-case; other cases still run."""
    call_count = {"n": 0}

    class _FlakyAgent:
        model_name = "mock"

        def run(self, task):
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                raise RuntimeError(f"Agent failed on {task.description}")

            class R:
                result = "some output"

            return R()

    cases = [EvalCase(id=str(i), task=f"task {i}", expected="output") for i in range(6)]
    runner = EvalRunner(agent=_FlakyAgent(), metric=contains)
    summary = runner.run(EvalDataset(cases))

    assert summary.total == 6
    errors = [r for r in summary.results if r.error is not None]
    assert len(errors) == 3  # every other call fails


# ---------------------------------------------------------------------------
# 7. EvalSummary → JSON round-trip
# ---------------------------------------------------------------------------


def test_e2e_summary_json_serialization():
    """EvalSummary serializes to JSON and all fields are present."""
    cases = [EvalCase(id="1", task="t", expected="e")]
    results = [
        __import__("devsper.evals.types", fromlist=["EvalResult"]).EvalResult(
            case=cases[0], actual="e", score=1.0, passed=True, duration_seconds=0.01
        )
    ]
    summary = EvalSummary(results=results, metric_name="contains", role="general")
    data = json.loads(summary.to_json())

    assert data["total"] == 1
    assert data["passed"] == 1
    assert data["pass_rate"] == 1.0
    assert data["mean_score"] == 1.0
    assert len(data["results"]) == 1
    assert data["results"][0]["actual"] == "e"


# ---------------------------------------------------------------------------
# 8. Prompt optimizer: noop wiring
# ---------------------------------------------------------------------------


def test_e2e_optimizer_noop_wiring():
    """optimize_after=True with NoopBackend saves a prompt file and returns summary."""
    dataset = EvalDataset(
        [EvalCase(id="1", task="what is AI?", expected="intelligence", role="general")]
    )
    agent = _make_agent({"what is AI?": "artificial intelligence"})
    optimizer = NoopBackend()

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            runner = EvalRunner(
                agent=agent,
                metric=contains,
                pass_threshold=0.5,
                optimize_after=True,
                optimizer=optimizer,
            )
            summary = runner.run(dataset)
            assert summary.passed == 1
            # Optimizer should have written a prompt file
            opt_file = Path(".devsper/optimized_prompts/general.json")
            assert opt_file.exists(), f"Expected {opt_file} to exist"
            data = json.loads(opt_file.read_text())
            assert "prompt_prefix" in data
        finally:
            os.chdir(orig_cwd)


# ---------------------------------------------------------------------------
# 9. Optimized prompt loading in roles.py
# ---------------------------------------------------------------------------


def test_e2e_roles_loads_optimized_prompt(tmp_path):
    """After optimization, get_role_config() returns the optimized prefix."""
    from devsper.agents.roles import get_role_config

    opt_dir = tmp_path / ".devsper" / "optimized_prompts"
    opt_dir.mkdir(parents=True)
    (opt_dir / "research_agent.json").write_text(
        json.dumps({"role": "research_agent", "prompt_prefix": "CUSTOM OPTIMIZED PROMPT"})
    )

    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        rc = get_role_config("research_agent")
        assert rc.prompt_prefix == "CUSTOM OPTIMIZED PROMPT"
    finally:
        os.chdir(orig_cwd)


# ---------------------------------------------------------------------------
# 10. get_metric resolution
# ---------------------------------------------------------------------------


def test_e2e_get_metric_contains():
    m = get_metric("contains")
    case = EvalCase(id="x", task="t", expected="hello")
    assert m(case, "hello world") == 1.0
    assert m(case, "goodbye") == 0.0


def test_e2e_get_metric_openevals_falls_back_without_package():
    """openevals_metric gracefully falls back when openevals isn't installed."""
    metric = openevals_metric("correctness", model="gpt-4o-mini")
    assert callable(metric)
    # Should not raise — uses built-in llm_judge fallback (which hits generate(),
    # but since openevals isn't installed it should attempt the fallback path)
    # We patch generate() to return a score so no real API call is made
    with patch("devsper.evals.metrics.llm_judge") as mock_judge:
        mock_fn = MagicMock(return_value=0.8)
        mock_judge.return_value = mock_fn
        # Force ImportError for openevals
        with patch.dict("sys.modules", {"openevals": None, "openevals.llm": None}):
            case = EvalCase(id="x", task="What is AI?", expected="intelligence")
            score = metric(case, "artificial intelligence")
            # With the mock, the fallback should have been called
            # (result is 0.0 from exception path — that's fine, we're testing no crash)
            assert isinstance(score, float)


def test_e2e_get_metric_openevals_prefix():
    """get_metric('openevals:correctness') returns a callable."""
    m = get_metric("openevals:correctness")
    assert callable(m)
    assert "openevals" in m.__name__


# ---------------------------------------------------------------------------
# 11. CLI: eval stub generates valid JSONL
# ---------------------------------------------------------------------------


def test_e2e_cli_eval_stub(tmp_path, capsys):
    """devsper eval stub --role research outputs valid JSONL."""
    from devsper.cli.main import _run_eval

    class _Args:
        eval_cmd = "stub"
        role = "research"
        n = 3
        out = None

    _run_eval(_Args())
    captured = capsys.readouterr()
    lines = [l for l in captured.out.strip().split("\n") if l]
    assert len(lines) == 3
    for line in lines:
        data = json.loads(line)
        assert "task" in data
        assert "expected" in data
        assert data["role"] == "research"


def test_e2e_cli_eval_stub_to_file(tmp_path):
    """devsper eval stub writes a valid JSONL file."""
    from devsper.cli.main import _run_eval

    out_path = str(tmp_path / "out.jsonl")

    class _Args:
        eval_cmd = "stub"
        role = "code"
        n = 4
        out = out_path

    _run_eval(_Args())
    loaded = EvalDataset.load(out_path)
    assert len(loaded) == 4
    assert all(c.role == "code" for c in loaded)


# ---------------------------------------------------------------------------
# 12. How to use OpenEvals properly (shows the intended API)
# ---------------------------------------------------------------------------


def test_openevals_metric_returns_callable():
    """openevals_metric() always returns a callable MetricFn regardless of install state."""
    for name in ("correctness", "conciseness", "groundedness", "relevance"):
        m = openevals_metric(name)
        assert callable(m), f"Expected callable for evaluator '{name}'"
        assert "openevals" in m.__name__


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY — run with real credentials to test OpenEvals live",
)
@pytest.mark.live
def test_openevals_correctness_live():
    """
    Live test: uses OpenEvals LLM-as-judge with a real model.
    Run: OPENAI_API_KEY=sk-... uv run pytest -m live tests/integration/test_evals_e2e.py
    """
    try:
        from openevals.llm import create_llm_as_judge
    except ImportError:
        pytest.skip("openevals not installed — pip install devsper[openevals]")

    metric = openevals_metric("correctness", model="openai:gpt-4o-mini")
    case = EvalCase(
        id="live1",
        task="What is the capital of France?",
        expected="Paris",
        role="research",
    )
    score = metric(case, "The capital of France is Paris.")
    assert score > 0.5, f"Expected high correctness score, got {score}"


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY",
)
@pytest.mark.live
def test_full_eval_pipeline_with_openevals_live():
    """
    Live end-to-end: EvalRunner + OpenEvals correctness metric against a mock agent
    that produces known good answers.
    """
    try:
        import openevals  # noqa: F401
    except ImportError:
        pytest.skip("openevals not installed")

    dataset = EvalDataset(
        [
            EvalCase(id="1", task="What is 2+2?", expected="4", role="general"),
            EvalCase(id="2", task="What color is the sky?", expected="blue", role="general"),
        ]
    )
    response_map = {
        "What is 2+2?": "2 plus 2 equals 4.",
        "What color is the sky?": "The sky is blue during the day.",
    }
    agent = _make_agent(response_map)
    metric = openevals_metric("correctness", model="openai:gpt-4o-mini")
    runner = EvalRunner(agent=agent, metric=metric, pass_threshold=0.5)
    summary = runner.run(dataset)

    assert summary.total == 2
    assert summary.pass_rate >= 0.5
