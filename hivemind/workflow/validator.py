"""Validate workflow definition: references, DAG, conditions, dead output."""

import re
from dataclasses import dataclass

from hivemind.workflow.resolver import build_execution_order, validate_dag
from hivemind.workflow.schema import WorkflowDefinition, WorkflowStep


@dataclass
class ValidationReport:
    valid: bool
    errors: list[str]  # blockers
    warnings: list[str]  # non-fatal issues
    info: list[str]  # stats/notes


def _template_refs(template: str) -> list[tuple[str, str]]:
    """Return list of (step_id, field) for references like steps.STEP_ID.FIELD or steps.STEP_ID.result."""
    refs: list[tuple[str, str]] = []
    # Match {steps.STEP_ID.FIELD} or {steps.STEP_ID.result}
    for m in re.finditer(r"\{steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z0-9_]+)\}", template):
        refs.append((m.group(1), m.group(2)))
    return refs


def _condition_ref(expression: str) -> tuple[str, str] | None:
    """Return (step_id, field) if expression is steps.STEP_ID.FIELD <op> value."""
    m = re.match(
        r"^\s*steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s",
        expression.strip(),
    )
    if m:
        return (m.group(1), m.group(2))
    return None


def validate_workflow(definition: WorkflowDefinition) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    step_ids = {s.id for s in definition.steps}
    step_by_id = {s.id: s for s in definition.steps}

    # DAG and depends_on
    dag_errors = validate_dag(definition.steps)
    errors.extend(dag_errors)

    waves = None
    if not dag_errors:
        try:
            waves = build_execution_order(definition.steps)
            info.append(f"Total steps: {len(definition.steps)}")
            info.append(f"Parallel waves: {len(waves)}")
            info.append(f"Critical path length: {len(waves)}")
        except Exception as e:
            errors.append(str(e))

    # All {steps.X.field} template references point to steps with output_schema defining that field (or .result)
    for step in definition.steps:
        for step_id, field in _template_refs(step.task):
            if step_id not in step_ids:
                errors.append(
                    f"Step {step.id!r} task references steps.{step_id}.{field} but step {step_id!r} does not exist."
                )
            else:
                ref_step = step_by_id[step_id]
                if field == "result":
                    continue  # always valid
                if not ref_step.output_schema:
                    errors.append(
                        f"Step {step.id!r} task references steps.{step_id}.{field} but step {step_id!r} has no output_schema."
                    )
                else:
                    names = [f.name for f in ref_step.output_schema]
                    if field not in names:
                        errors.append(
                            f"Step {step.id!r} task references steps.{step_id}.{field} but step {step_id!r} output_schema has: {names}."
                        )

    # All if: expressions reference steps that appear earlier in dependency order
    # and output_schema fields referenced in conditions exist
    if waves:
        order_so_far: set[str] = set()
        for wave in waves:
            for s in wave:
                if s.if_:
                    ref = _condition_ref(s.if_.expression)
                    if ref:
                        cond_step_id, cond_field = ref
                        if cond_step_id not in order_so_far:
                            errors.append(
                                f"Step {s.id!r} condition references steps.{cond_step_id}.{cond_field} "
                                f"but {cond_step_id!r} is not a dependency (must run before this step)."
                            )
                        elif cond_step_id in step_by_id:
                            cond_step = step_by_id[cond_step_id]
                            if cond_field != "result":
                                names = [f.name for f in cond_step.output_schema]
                                if cond_field not in names:
                                    errors.append(
                                        f"Step {s.id!r} condition references steps.{cond_step_id}.{cond_field} "
                                        f"but that step's output_schema has: {names}."
                                    )
                order_so_far.add(s.id)

    # Warning: steps with no id set (we require id; no auto-generated opaque ids in schema)
    # Our schema requires id, so skip.

    # Warning: steps with output_schema but no downstream steps that use the output (dead output)
    consumers: dict[str, set[str]] = {sid: set() for sid in step_ids}
    for step in definition.steps:
        for step_id, field in _template_refs(step.task):
            if step_id in step_ids:
                consumers[step_id].add(step.id)
    for step in definition.steps:
        if step.output_schema and step.id in consumers and not consumers[step.id]:
            warnings.append(
                f"Step {step.id!r} has output_schema but no downstream step uses its output (dead output)."
            )

    return ValidationReport(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        info=info,
    )
