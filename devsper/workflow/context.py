"""WorkflowContext: typed output passing between steps."""

import re
from typing import Any

from pydantic import BaseModel


class WorkflowTemplateError(Exception):
    """Raised when a template reference cannot be resolved."""

    pass


class StepResult(BaseModel):
    step_id: str
    raw_result: str  # full agent output
    structured: dict | None = None  # parsed output_schema result, if defined
    skipped: bool = False
    error: str | None = None
    duration_seconds: float = 0.0


class WorkflowContext:
    def __init__(self, inputs: dict[str, Any]) -> None:
        self.inputs = inputs
        self.steps: dict[str, StepResult] = {}

    def record(self, step_id: str, result: StepResult) -> None:
        self.steps[step_id] = result

    def resolve_template(self, template: str) -> str:
        """
        Replace {input.field} with self.inputs[field].
        Replace {steps.step_id.result} with self.steps[step_id].raw_result.
        Replace {steps.step_id.field} with self.steps[step_id].structured[field].
        Raise WorkflowTemplateError if reference not found.
        """
        # Match {input.NAME} or {steps.STEP_ID.result} or {steps.STEP_ID.FIELD}
        pattern = re.compile(
            r"\{(\w+)\.([^}]+)\}"
        )  # group 1: input|steps, group 2: rest

        def repl(match: re.Match[str]) -> str:
            prefix, rest = match.group(1), match.group(2)
            if prefix == "input":
                if rest not in self.inputs:
                    raise WorkflowTemplateError(
                        f"Template references input.{rest} but input {rest!r} is not provided. "
                        f"Available: {list(self.inputs.keys())}"
                    )
                val = self.inputs[rest]
                return str(val) if val is not None else ""
            if prefix == "steps":
                part = rest.split(".", 1)
                if len(part) != 2:
                    raise WorkflowTemplateError(
                        f"Invalid steps reference: {match.group(0)}. "
                        "Use steps.<step_id>.result or steps.<step_id>.<field>"
                    )
                step_id, field = part[0], part[1]
                if step_id not in self.steps:
                    raise WorkflowTemplateError(
                        f"Template references steps.{step_id}.{field} but step {step_id!r} "
                        f"has not run yet or does not exist. Available: {list(self.steps.keys())}"
                    )
                sr = self.steps[step_id]
                if field == "result":
                    return sr.raw_result or ""
                if sr.structured is not None and field in sr.structured:
                    val = sr.structured[field]
                    return str(val) if val is not None else ""
                raise WorkflowTemplateError(
                    f"Template references steps.{step_id}.{field} but step {step_id!r} "
                    f"has no structured field {field!r}. "
                    f"Available: result, or {list(sr.structured.keys()) if sr.structured else []}"
                )
            raise WorkflowTemplateError(f"Unknown template prefix: {prefix!r}")

        return pattern.sub(repl, template)

    def get_field(self, step_id: str, field: str) -> Any:
        """Used by condition evaluator. Returns None if step/field missing."""
        if step_id not in self.steps:
            return None
        sr = self.steps[step_id]
        if field == "result":
            return sr.raw_result
        if sr.structured is not None and field in sr.structured:
            return sr.structured[field]
        return None

    def to_summary(self) -> dict[str, Any]:
        """Serializable summary for output/replay."""
        steps_summary: dict[str, dict[str, Any]] = {}
        for sid, sr in self.steps.items():
            steps_summary[sid] = {
                "step_id": sr.step_id,
                "skipped": sr.skipped,
                "error": sr.error,
                "duration_seconds": sr.duration_seconds,
                "has_result": bool(sr.raw_result),
                "has_structured": sr.structured is not None,
            }
        return {
            "inputs": dict(self.inputs),
            "steps": steps_summary,
        }
