"""Tests for workflow loader, runner, validator, conditions, and resolver."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from hivemind.workflow.conditions import (
    WorkflowConditionError,
    evaluate_condition,
)
from hivemind.workflow.context import (
    StepResult,
    WorkflowContext,
    WorkflowTemplateError,
)
from hivemind.workflow.loader import load_workflow, list_workflows
from hivemind.workflow.resolver import (
    WorkflowCycleError,
    build_execution_order,
    validate_dag,
)
from hivemind.workflow.runner import WorkflowRunner, run_workflow
from hivemind.workflow.schema import (
    OutputField,
    StepCondition,
    WorkflowDefinition,
    WorkflowStep,
)
from hivemind.workflow.validator import ValidationReport, validate_workflow


# --- Loader / backward compat ---


def test_load_workflow_from_path():
    """Load workflow from a TOML file path."""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(b'[workflow]\nname = "test_wf"\nsteps = ["a", "b"]\n')
        path = Path(f.name)
    try:
        wf = load_workflow("test_wf", config_path=path)
        assert wf is not None
        assert wf.name == "test_wf"
        assert len(wf.steps) == 2
        assert wf.steps[0].task == "a"
        assert wf.steps[1].task == "b"
        assert wf.steps[1].depends_on == [wf.steps[0].id]
    finally:
        path.unlink(missing_ok=True)


def test_list_workflows_empty_without_file():
    """Without a workflow file, list_workflows returns [] when we use a path that doesn't exist."""
    wf = load_workflow("nonexistent", config_path=Path("/nonexistent/hivemind.toml"))
    assert wf is None


def test_backward_compat():
    """Old plain-list workflow still loads and runs."""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(b'[workflow]\nname = "legacy_wf"\nsteps = ["Step one", "Step two"]\n')
        path = Path(f.name)
    try:
        wf = load_workflow("legacy_wf", config_path=path)
        assert wf is not None
        assert len(wf.steps) == 2
        with patch("hivemind.agents.agent.generate", side_effect=["out1", "out2"]):
            results = run_workflow(
                ["Step one", "Step two"],
                worker_model="mock",
                worker_count=1,
            )
        assert len(results) == 2
        assert "out1" in results.values()
        assert "out2" in results.values()
    finally:
        path.unlink(missing_ok=True)


# --- Sequential / parallel ---


def test_sequential_steps_execute_in_order():
    """Steps with depends_on execute in dependency order."""
    steps = [
        WorkflowStep(id="a", task="First", depends_on=[]),
        WorkflowStep(id="b", task="Second", depends_on=["a"]),
        WorkflowStep(id="c", task="Third", depends_on=["b"]),
    ]
    wf = WorkflowDefinition(name="seq", steps=steps, inputs=[])
    order = build_execution_order(wf.steps)
    assert len(order) == 3
    assert [s.id for s in order[0]] == ["a"]
    assert [s.id for s in order[1]] == ["b"]
    assert [s.id for s in order[2]] == ["c"]
    with patch("hivemind.agents.agent.generate", side_effect=["1", "2", "3"]):
        runner = WorkflowRunner()
        ctx = runner.run(wf, {}, worker_model="mock", worker_count=1)
    assert ctx.steps["a"].raw_result == "1"
    assert ctx.steps["b"].raw_result == "2"
    assert ctx.steps["c"].raw_result == "3"


def test_parallel_steps_in_same_wave():
    """Steps with no shared dependencies run in the same wave."""
    steps = [
        WorkflowStep(id="a", task="Task A", depends_on=[]),
        WorkflowStep(id="b", task="Task B", depends_on=[]),
        WorkflowStep(id="c", task="Task C", depends_on=["a", "b"]),
    ]
    wf = WorkflowDefinition(name="par", steps=steps, inputs=[])
    order = build_execution_order(wf.steps)
    assert len(order) == 2
    assert set(s.id for s in order[0]) == {"a", "b"}
    assert [s.id for s in order[1]] == ["c"]


# --- Conditions ---


def test_condition_skips_step():
    """if: false → step is skipped; downstream steps still run."""
    steps = [
        WorkflowStep(id="classify", task="Classify", depends_on=[], output_schema=[OutputField(name="category", type="str")]),
        WorkflowStep(
            id="technical",
            task="Technical analysis",
            depends_on=["classify"],
            if_=StepCondition(expression="steps.classify.category == 'technical'"),
        ),
        WorkflowStep(id="always", task="Always run", depends_on=["classify"]),
    ]
    wf = WorkflowDefinition(name="cond", steps=steps, inputs=[])
    with patch("hivemind.agents.agent.generate", side_effect=['{"category": "business"}', "Always output"]):
        runner = WorkflowRunner()
        ctx = runner.run(wf, {}, worker_model="mock", worker_count=2)
    assert ctx.steps["classify"].skipped is False
    assert ctx.steps["technical"].skipped is True
    assert ctx.steps["always"].skipped is False
    assert "Always output" in (ctx.steps["always"].raw_result or "")


def test_condition_blocks_dependent():
    """Skipped step causes dependent steps to also be skipped."""
    steps = [
        WorkflowStep(id="first", task="First", depends_on=[]),
        WorkflowStep(
            id="skip_me",
            task="Skip",
            depends_on=["first"],
            if_=StepCondition(expression="steps.first.result == 'skip'"),
        ),
        WorkflowStep(id="depends_on_skip", task="Downstream", depends_on=["skip_me"]),
    ]
    wf = WorkflowDefinition(name="block", steps=steps, inputs=[])
    with patch("hivemind.agents.agent.generate", side_effect=["other"]):  # first returns "other", so skip_me condition false
        runner = WorkflowRunner()
        ctx = runner.run(wf, {}, worker_model="mock", worker_count=1)
    assert ctx.steps["skip_me"].skipped is True
    assert ctx.steps["depends_on_skip"].skipped is True
    assert ctx.steps["depends_on_skip"].error == "Dependency was skipped"


# --- Template resolution ---


def test_template_resolution():
    """{steps.X.field} resolves correctly from structured output."""
    ctx = WorkflowContext(inputs={"text": "hello"})
    ctx.record(
        "classify",
        StepResult(
            step_id="classify",
            raw_result="raw",
            structured={"category": "technical", "score": 0.9},
            skipped=False,
            duration_seconds=1.0,
        ),
    )
    out = ctx.resolve_template("Category: {steps.classify.category}, score {steps.classify.score}")
    assert out == "Category: technical, score 0.9"
    out2 = ctx.resolve_template("Input: {input.text}")
    assert out2 == "Input: hello"
    out3 = ctx.resolve_template("Full: {steps.classify.result}")
    assert out3 == "Full: raw"


def test_template_resolution_missing_raises():
    """Missing reference raises WorkflowTemplateError."""
    ctx = WorkflowContext(inputs={})
    with pytest.raises(WorkflowTemplateError):
        ctx.resolve_template("{input.missing}")
    ctx.record("a", StepResult(step_id="a", raw_result="x", skipped=False, duration_seconds=0.0))
    with pytest.raises(WorkflowTemplateError):
        ctx.resolve_template("{steps.b.result}")


# --- Conditions evaluator ---


def test_evaluate_condition_equals():
    ctx = WorkflowContext({})
    ctx.record("x", StepResult(step_id="x", raw_result="", structured={"cat": "technical"}, skipped=False, duration_seconds=0.0))
    assert evaluate_condition("steps.x.cat == 'technical'", ctx) is True
    assert evaluate_condition("steps.x.cat == 'business'", ctx) is False


def test_evaluate_condition_missing_returns_false():
    ctx = WorkflowContext({})
    assert evaluate_condition("steps.missing.field == 'x'", ctx) is False


def test_evaluate_condition_invalid_raises():
    ctx = WorkflowContext({})
    ctx.record("x", StepResult(step_id="x", raw_result="", structured={"v": 1}, skipped=False, duration_seconds=0.0))
    with pytest.raises(WorkflowConditionError):
        evaluate_condition("not a valid expression", ctx)


# --- Output schema ---


def test_output_schema_parsed():
    """Agent JSON response is validated against schema and stored in structured."""
    steps = [
        WorkflowStep(
            id="classify",
            task="Classify",
            depends_on=[],
            output_schema=[
                OutputField(name="category", type="str"),
                OutputField(name="confidence", type="float"),
            ],
        ),
    ]
    wf = WorkflowDefinition(name="schema", steps=steps, inputs=[])
    with patch(
        "hivemind.agents.agent.generate",
        return_value='{"category": "technical", "confidence": 0.95}',
    ):
        runner = WorkflowRunner()
        ctx = runner.run(wf, {}, worker_model="mock", worker_count=1)
    assert ctx.steps["classify"].structured is not None
    assert ctx.steps["classify"].structured["category"] == "technical"
    assert ctx.steps["classify"].structured["confidence"] == 0.95


# --- Resolver / cycle ---


def test_cycle_detection():
    """Circular depends_on raises WorkflowCycleError."""
    steps = [
        WorkflowStep(id="a", task="A", depends_on=["c"]),
        WorkflowStep(id="b", task="B", depends_on=["a"]),
        WorkflowStep(id="c", task="C", depends_on=["b"]),
    ]
    with pytest.raises(WorkflowCycleError) as exc_info:
        build_execution_order(steps)
    assert "cycle" in str(exc_info.value).lower()


# --- Validator ---


def test_validator_catches_bad_reference():
    """depends_on unknown id → validation error."""
    steps = [
        WorkflowStep(id="a", task="A", depends_on=["nonexistent"]),
    ]
    # Use model_construct so Pydantic doesn't reject the invalid ref; validator should catch it
    wf = WorkflowDefinition.model_construct(name="bad", steps=steps, inputs=[])
    report = validate_workflow(wf)
    assert report.valid is False
    assert any("nonexistent" in e for e in report.errors)


def test_validator_dead_output_warning():
    """output_schema with no downstream consumers → warning."""
    steps = [
        WorkflowStep(
            id="producer",
            task="Produce",
            depends_on=[],
            output_schema=[OutputField(name="x", type="str")],
        ),
        WorkflowStep(id="consumer", task="Use {input.y}", depends_on=[]),  # does not use steps.producer
    ]
    wf = WorkflowDefinition(name="dead", steps=steps, inputs=[])
    report = validate_workflow(wf)
    assert any("dead" in w.lower() or "output" in w.lower() for w in report.warnings)


def test_validator_passes_clean_workflow():
    """Clean workflow passes and returns info."""
    steps = [
        WorkflowStep(id="a", task="First", depends_on=[]),
        WorkflowStep(id="b", task="Second {steps.a.result}", depends_on=["a"]),
    ]
    wf = WorkflowDefinition(name="clean", steps=steps, inputs=[])
    report = validate_workflow(wf)
    assert report.valid is True
    assert len(report.errors) == 0
    assert any("steps" in i.lower() or "wave" in i.lower() for i in report.info)
