"""Pipeline engine: typed outputs, branching, dependencies, retries."""

import asyncio
import json
import re
import time
from typing import Any

from hivemind.types.task import Task
from hivemind.workflow.conditions import evaluate_condition
from hivemind.workflow.context import StepResult, WorkflowContext, WorkflowTemplateError
from hivemind.workflow.resolver import WorkflowCycleError, build_execution_order
from hivemind.workflow.schema import OutputField, WorkflowDefinition, WorkflowStep
from hivemind.utils.models import resolve_model
from hivemind.utils.event_logger import EventLog


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


def _parse_structured_output(
    raw_result: str, output_schema: list[OutputField]
) -> dict[str, Any]:
    """Extract JSON from raw result and validate against output_schema. Returns dict or raises."""
    # Try to find a JSON object in the response
    stripped = raw_result.strip()
    # Allow ```json ... ``` or bare { ... }
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            data = {}
    else:
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = {}

    out: dict[str, Any] = {}
    for f in output_schema:
        if f.name not in data and f.required:
            raise ValueError(f"Missing required field {f.name!r} in structured output")
        val = data.get(f.name)
        out[f.name] = _coerce_value(val, f.type) if val is not None else (None if not f.required else _coerce_value(None, f.type))
    return out


def _run_single_step_sync(
    step: WorkflowStep,
    context: WorkflowContext,
    worker_model: str,
    worker_count: int,
    memory_router: Any,
    use_tools: bool,
    event_log: Any,
) -> StepResult:
    """Run one step synchronously (resolve template, call agent, parse output). Used from async via to_thread."""
    from hivemind.agents.agent import Agent
    from hivemind.reasoning.store import ReasoningStore
    from hivemind.swarm.executor import Executor
    from hivemind.swarm.scheduler import Scheduler

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

                async def _run_wave() -> list[StepResult]:
                    return await asyncio.gather(
                        *[
                            _run_step_with_retry(
                                step,
                                context,
                                worker_model,
                                worker_count,
                                memory_router,
                                use_tools,
                                event_log or EventLog(),
                                asyncio.get_running_loop(),
                            )
                            for step in to_run
                        ]
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
    from hivemind.workflow.loader import _workflow_from_legacy_steps
    from hivemind.workflow.schema import WorkflowDefinition

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
