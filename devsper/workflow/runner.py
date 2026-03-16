"""Pipeline engine: typed outputs, branching, dependencies, retries."""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from devsper.types.task import Task
from devsper.types.event import Event, events
from devsper.workflow.conditions import evaluate_condition
from devsper.workflow.context import StepResult, WorkflowContext, WorkflowTemplateError
from devsper.workflow.resolver import WorkflowCycleError, build_execution_order
from devsper.workflow.schema import OutputField, WorkflowDefinition, WorkflowStep
from devsper.utils.models import resolve_model
from devsper.utils.event_logger import EventLog
from datetime import datetime, timezone


class WorkflowStepError(Exception):
    """Raised when a workflow step fails after all retries (e.g. structured output)."""
    pass


@dataclass
class ParseResult:
    success: bool
    data: dict[str, Any] | None
    error: str | None
    missing_fields: list[str]
    type_errors: list[str]


def _validate_inputs(workflow: WorkflowDefinition, inputs: dict[str, Any]) -> None:
    """Validate runtime inputs against workflow.inputs schema. Raises ValueError on failure."""
    for field in workflow.inputs:
        if field.required and field.name not in inputs:
            raise ValueError(
                f"Required input {field.name!r} not provided. Required: {[f.name for f in workflow.inputs if f.required]}"
            )


def _coerce_value(val: Any, type_name: str) -> Any:
    """Coerce value to output_schema type."""
    if type_name == "str":
        return str(val) if val is not None else ""
    if type_name == "int":
        return int(val) if val is not None else 0
    if type_name == "float":
        return float(val) if val is not None else 0.0
    if type_name == "bool":
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")
    if type_name == "list":
        return list(val) if isinstance(val, (list, tuple)) else [val]
    if type_name == "dict":
        return dict(val) if isinstance(val, dict) else {}
    return val


def _strip_markdown_json(raw: str) -> str:
    """Strip markdown code fences (```json ... ```) if present."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        first = stripped.find("\n")
        if first != -1 and "json" in stripped[:first].lower():
            stripped = stripped[first + 1 :]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
    return stripped


def try_parse_structured(
    raw: str, schema: list[OutputField]
) -> ParseResult:
    """
    Parse raw string as JSON and validate against schema.
    Returns ParseResult(success, data, error, missing_fields, type_errors).
    """
    raw = _strip_markdown_json(raw)
    missing: list[str] = []
    type_errors: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return ParseResult(
            success=False,
            data=None,
            error=str(e),
            missing_fields=[],
            type_errors=[],
        )
    if not isinstance(data, dict):
        return ParseResult(
            success=False,
            data=None,
            error="Root is not a JSON object",
            missing_fields=[],
            type_errors=[],
        )
    for f in schema:
        if f.name not in data:
            if f.required:
                missing.append(f.name)
            continue
        val = data[f.name]
        expected = f.type
        if expected == "str" and not isinstance(val, str):
            type_errors.append(f"{f.name}: expected str")
        elif expected == "int" and not isinstance(val, int):
            type_errors.append(f"{f.name}: expected int")
        elif expected == "float" and not isinstance(val, (int, float)):
            type_errors.append(f"{f.name}: expected float")
        elif expected == "bool" and not isinstance(val, bool):
            type_errors.append(f"{f.name}: expected bool")
        elif expected == "list" and not isinstance(val, list):
            type_errors.append(f"{f.name}: expected list")
        elif expected == "dict" and not isinstance(val, dict):
            type_errors.append(f"{f.name}: expected dict")
    if missing or type_errors:
        err_parts = []
        if missing:
            err_parts.append(f"missing: {', '.join(missing)}")
        if type_errors:
            err_parts.append(f"type errors: {'; '.join(type_errors)}")
        return ParseResult(
            success=False,
            data=None,
            error="; ".join(err_parts),
            missing_fields=missing,
            type_errors=type_errors,
        )
    out: dict[str, Any] = {}
    for f in schema:
        val = data.get(f.name)
        out[f.name] = (
            _coerce_value(val, f.type)
            if val is not None
            else (None if not f.required else _coerce_value(None, f.type))
        )
    return ParseResult(
        success=True,
        data=out,
        error=None,
        missing_fields=[],
        type_errors=[],
    )


def _format_schema(output_schema: list[OutputField]) -> str:
    """Format output_schema for inclusion in correction prompt."""
    lines = []
    for f in output_schema:
        req = "required" if f.required else "optional"
        lines.append(f"  {f.name} ({f.type}, {req})")
    return "\n".join(lines) if lines else "{}"


def _parse_structured_output(
    raw_result: str, output_schema: list[OutputField]
) -> dict[str, Any]:
    """Extract JSON from raw result and validate against output_schema. Returns dict or raises."""
    pr = try_parse_structured(raw_result, output_schema)
    if not pr.success:
        raise ValueError(pr.error or "Parse failed")
    return pr.data or {}


def _run_single_step_sync(
    step: WorkflowStep,
    context: WorkflowContext,
    worker_model: str,
    worker_count: int,
    memory_router: Any,
    use_tools: bool,
    event_log: Any,
    task_description_override: str | None = None,
) -> StepResult:
    """Run one step synchronously (resolve template, call agent, parse output). Used from async via to_thread.
    If task_description_override is set, use it as the task description instead of resolving step.task."""
    from devsper.agents.agent import Agent
    from devsper.reasoning.store import ReasoningStore
    from devsper.swarm.executor import Executor
    from devsper.swarm.scheduler import Scheduler

    start = time.perf_counter()
    if task_description_override is not None:
        resolved_task = task_description_override
    else:
        try:
            resolved_task = context.resolve_template(step.task)
        except WorkflowTemplateError as e:
            return StepResult(
                step_id=step.id,
                raw_result="",
                structured=None,
                skipped=False,
                error=str(e),
                duration_seconds=time.perf_counter() - start,
            )

        if step.output_schema:
            field_names = ", ".join(f.name for f in step.output_schema)
            resolved_task += (
                f"\n\nRespond ONLY with a JSON object with these fields: {field_names}. "
                "Do not include any other text."
            )

    model = resolve_model(step.model or worker_model, "analysis")
    task = Task(
        id=step.id,
        description=resolved_task,
        dependencies=[],
        role=step.role,
    )
    scheduler = Scheduler()
    scheduler.add_tasks([task])
    reasoning_store = ReasoningStore()
    agent = Agent(
        model_name=model,
        event_log=event_log,
        memory_router=memory_router,
        store_result_to_memory=False,
        use_tools=use_tools,
        reasoning_store=reasoning_store,
        user_task=resolved_task[:200],
    )
    executor = Executor(
        scheduler=scheduler,
        agent=agent,
        worker_count=min(worker_count, 1),  # one task
        event_log=event_log,
    )
    executor.run_sync()
    results = scheduler.get_results()
    raw_result = results.get(step.id, "")

    structured: dict[str, Any] | None = None
    if step.output_schema and raw_result:
        try:
            structured = _parse_structured_output(raw_result, step.output_schema)
        except (ValueError, json.JSONDecodeError) as e:
            return StepResult(
                step_id=step.id,
                raw_result=raw_result,
                structured=None,
                skipped=False,
                error=f"Failed to parse output_schema: {e}",
                duration_seconds=time.perf_counter() - start,
            )

    return StepResult(
        step_id=step.id,
        raw_result=raw_result or "",
        structured=structured,
        skipped=False,
        error=None,
        duration_seconds=time.perf_counter() - start,
    )


async def _run_step_with_correction(
    step: WorkflowStep,
    context: WorkflowContext,
    worker_model: str,
    worker_count: int,
    memory_router: Any,
    use_tools: bool,
    event_log: Any,
    loop: asyncio.AbstractEventLoop,
) -> StepResult:
    """Run step with structured output self-correction: on parse failure, retry with correction prompt."""
    start = time.perf_counter()
    try:
        resolved_task = context.resolve_template(step.task)
    except WorkflowTemplateError as e:
        return StepResult(
            step_id=step.id,
            raw_result="",
            structured=None,
            skipped=False,
            error=str(e),
            duration_seconds=time.perf_counter() - start,
        )

    if step.output_schema:
        field_names = ", ".join(f.name for f in step.output_schema)
        task_prompt = (
            resolved_task
            + f"\n\nRespond ONLY with a JSON object with these fields: {field_names}. "
            "Do not include any other text."
        )
    else:
        task_prompt = resolved_task

    last_error: str | None = None
    for attempt in range(step.retry + 1):
        result = await loop.run_in_executor(
            None,
            _run_single_step_sync,
            step,
            context,
            worker_model,
            worker_count,
            memory_router,
            use_tools,
            event_log,
            task_prompt,
        )
        if result.error and not step.output_schema:
            last_error = result.error
            if attempt < step.retry:
                await asyncio.sleep(2**attempt)
            continue
        if not step.output_schema:
            return result

        parse_result = try_parse_structured(result.raw_result or "", step.output_schema)
        if parse_result.success and parse_result.data is not None:
            return StepResult(
                step_id=step.id,
                raw_result=result.raw_result or "",
                structured=parse_result.data,
                skipped=False,
                error=None,
                duration_seconds=time.perf_counter() - start,
            )

        if event_log:
            event_log.append_event(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    type=events.TASK_STRUCTURED_OUTPUT_CORRECTED,
                    payload={
                        "task_id": step.id,
                        "step_id": step.id,
                        "attempt": attempt + 1,
                        "error_summary": parse_result.error,
                    },
                )
            )
        correction_context = f"""
Your previous response could not be parsed. Error: {parse_result.error or 'Unknown'}

Required JSON schema:
{_format_schema(step.output_schema)}

Common mistakes:
- Extra text before/after the JSON
- Missing required fields: {parse_result.missing_fields}
- Wrong types: {parse_result.type_errors}

Please respond ONLY with valid JSON matching the schema above.
"""
        task_prompt = f"{resolved_task}\n\n{correction_context}"
        last_error = parse_result.error

    raise WorkflowStepError(
        f"Step {step.id} failed structured output after {step.retry + 1} attempts: {last_error}"
    )


async def _run_step_with_retry(
    step: WorkflowStep,
    context: WorkflowContext,
    worker_model: str,
    worker_count: int,
    memory_router: Any,
    use_tools: bool,
    event_log: Any,
    loop: asyncio.AbstractEventLoop,
) -> StepResult:
    """Run step with retries and exponential backoff."""
    last_error: str | None = None
    for attempt in range(step.retry + 1):
        try:
            result = await loop.run_in_executor(
                None,
                _run_single_step_sync,
                step,
                context,
                worker_model,
                worker_count,
                memory_router,
                use_tools,
                event_log,
            )
            if result.error and attempt < step.retry:
                last_error = result.error
                await asyncio.sleep(2**attempt)
                continue
            return result
        except Exception as e:
            last_error = str(e)
            if attempt < step.retry:
                await asyncio.sleep(2**attempt)
            else:
                return StepResult(
                    step_id=step.id,
                    raw_result="",
                    structured=None,
                    skipped=False,
                    error=last_error,
                    duration_seconds=0.0,
                )
    return StepResult(
        step_id=step.id,
        raw_result="",
        structured=None,
        skipped=False,
        error=last_error or "Unknown",
        duration_seconds=0.0,
    )


class WorkflowRunner:
    def run(
        self,
        workflow: WorkflowDefinition,
        inputs: dict[str, Any],
        worker_model: str = "mock",
        worker_count: int = 4,
        memory_router: Any = None,
        use_tools: bool = False,
        event_log: Any = None,
    ) -> WorkflowContext:
        """Execute workflow: validate inputs, run waves in order, steps in parallel within wave."""
        _validate_inputs(workflow, inputs)
        context = WorkflowContext(inputs)
        waves = build_execution_order(workflow.steps)
        for wave in waves:
                # Evaluate conditions and collect steps to run vs skip
                to_run: list[WorkflowStep] = []
                for step in wave:
                    # Skip if any dependency was skipped
                    if any(
                        context.steps.get(dep, StepResult(step_id=dep, raw_result="", skipped=True)).skipped
                        for dep in step.depends_on
                    ):
                        context.record(
                            step.id,
                            StepResult(
                                step_id=step.id,
                                raw_result="",
                                structured=None,
                                skipped=True,
                                error="Dependency was skipped",
                                duration_seconds=0.0,
                            ),
                        )
                        continue
                    if step.if_:
                        try:
                            if not evaluate_condition(step.if_.expression, context):
                                context.record(
                                    step.id,
                                    StepResult(
                                        step_id=step.id,
                                        raw_result="",
                                        structured=None,
                                        skipped=True,
                                        error=None,
                                        duration_seconds=0.0,
                                    ),
                                )
                                continue
                        except Exception:
                            # Conservative: skip on condition error
                            context.record(
                                step.id,
                                StepResult(
                                    step_id=step.id,
                                    raw_result="",
                                    structured=None,
                                    skipped=True,
                                    error="Condition evaluation failed",
                                    duration_seconds=0.0,
                                ),
                            )
                            continue
                    to_run.append(step)

                if not to_run:
                    continue

                log = event_log or EventLog()

                async def _run_one(step: WorkflowStep) -> StepResult:
                    loop = asyncio.get_running_loop()
                    if step.output_schema:
                        try:
                            return await _run_step_with_correction(
                                step,
                                context,
                                worker_model,
                                worker_count,
                                memory_router,
                                use_tools,
                                log,
                                loop,
                            )
                        except WorkflowStepError as e:
                            return StepResult(
                                step_id=step.id,
                                raw_result="",
                                structured=None,
                                skipped=False,
                                error=str(e),
                                duration_seconds=0.0,
                            )
                    return await _run_step_with_retry(
                        step,
                        context,
                        worker_model,
                        worker_count,
                        memory_router,
                        use_tools,
                        log,
                        loop,
                    )

                async def _run_wave() -> list[StepResult]:
                    return await asyncio.gather(
                        *[_run_one(step) for step in to_run]
                    )

                results = asyncio.run(_run_wave())
                for r in results:
                    context.record(r.step_id, r)
        return context


def run_workflow(
    steps: list[str],
    worker_model: str = "mock",
    worker_count: int = 2,
    event_log=None,
    memory_router=None,
    use_tools: bool = False,
) -> dict[str, str]:
    """
    Legacy: run a workflow from a list of task strings (sequential).
    For new workflows use WorkflowRunner with WorkflowDefinition.
    """
    from devsper.workflow.loader import _workflow_from_legacy_steps
    from devsper.workflow.schema import WorkflowDefinition

    definition = _workflow_from_legacy_steps(steps)
    runner = WorkflowRunner()
    ctx = runner.run(
        definition,
        inputs={},
        worker_model=worker_model,
        worker_count=worker_count,
        memory_router=memory_router,
        use_tools=use_tools,
        event_log=event_log,
    )
    # Return task_id -> result for backward compat
    return {sr.step_id: sr.raw_result for sr in ctx.steps.values()}
