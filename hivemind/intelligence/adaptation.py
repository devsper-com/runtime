"""
Self-optimizing swarm: adapt execution strategy in real time.

Detects slow tasks, failed tasks, and spawns alternative subtasks.
The adaptive planner can inject new tasks into the scheduler DAG.
"""

from datetime import datetime, timezone
from hivemind.types.task import Task, TaskStatus
from hivemind.swarm.scheduler import Scheduler


def detect_slow_tasks(
    scheduler: Scheduler,
    task_start_times: dict[str, datetime],
    threshold_seconds: float = 60.0,
    *,
    now: datetime | None = None,
) -> list[str]:
    """
    Return task ids that are still RUNNING and have been running longer than threshold_seconds.
    task_start_times maps task_id -> start time (e.g. when task was set to RUNNING).
    """
    now = now or datetime.now(timezone.utc)
    slow: list[str] = []
    for task_id, task in scheduler._tasks.items():
        if task.status != TaskStatus.RUNNING:
            continue
        start = task_start_times.get(task_id)
        if start is None:
            continue
        elapsed = (now - start).total_seconds()
        if elapsed >= threshold_seconds:
            slow.append(task_id)
    return slow


def detect_failed_tasks(scheduler: Scheduler) -> list[str]:
    """Return task ids that have status FAILED."""
    return [
        task_id
        for task_id, task in scheduler._tasks.items()
        if task.status == TaskStatus.FAILED
    ]


def suggest_alternative_tasks(
    task: Task,
    planner: object,
    context: list[Task] | None = None,
) -> list[Task]:
    """
    Ask the planner to suggest alternative follow-up tasks (e.g. after failure or timeout).
    Returns new tasks that depend on the same dependencies as the given task, so they
    can be injected as alternatives. The planner's expand_tasks is used with a synthetic
    "failed" result to get alternatives.
    """
    if not hasattr(planner, "expand_tasks"):
        return []
    # Create a minimal completed task with a note that original failed/timed out
    synthetic = Task(
        id=task.id + "_alt",
        description=f"(Alternative to failed/slow task) {task.description}",
        dependencies=task.dependencies.copy(),
        status=TaskStatus.COMPLETED,
        result="[Previous attempt failed or timed out. Suggest alternative approach.]",
    )
    return planner.expand_tasks(synthetic, context=context)


def create_alternative_subtasks_for_failed(
    failed_task: Task,
    planner: object,
    scheduler: Scheduler,
) -> list[Task]:
    """
    Generate alternative tasks for a failed task and return them (caller should
    add to scheduler via scheduler.add_tasks). New tasks depend on the same
    dependencies as the failed task so they can run in place of it.
    """
    new_tasks = suggest_alternative_tasks(failed_task, planner)
    if not new_tasks:
        return []
    # Ensure new tasks depend on same deps so they are runnable when failed_task's deps are done
    for t in new_tasks:
        if t.dependencies != failed_task.dependencies:
            t.dependencies = failed_task.dependencies.copy()
    return new_tasks
