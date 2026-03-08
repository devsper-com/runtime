"""
Speculative execution: predict likely next tasks and execute them early.

When planner produces DAG A → B → C:
- Run A
- Speculatively schedule B and C (they depend only on A)
- When A completes: confirm B and C (use speculative results) or discard
"""

from hivemind.types.task import Task, TaskStatus


def get_speculative_candidates(
    tasks: dict[str, Task],
    graph,
) -> list[Task]:
    """
    Return tasks that are candidates for speculative execution: all dependencies
    are either COMPLETED or exactly one is RUNNING (and we bet it will complete).
    graph must have .predecessors(node_id) returning an iterable of dependency ids.
    """
    candidates: list[Task] = []
    for task_id, task in tasks.items():
        if task.status != TaskStatus.PENDING:
            continue
        deps = list(graph.predecessors(task_id))
        if not deps:
            continue
        completed = sum(1 for d in deps if tasks[d].status == TaskStatus.COMPLETED)
        running = sum(1 for d in deps if tasks[d].status == TaskStatus.RUNNING)
        # Speculative: all deps done except one which is running
        if running == 1 and completed == len(deps) - 1:
            candidates.append(task)
    return candidates


def confirm_speculative(task: Task) -> None:
    """Mark a speculatively run task as confirmed (keep result)."""
    if task.speculative and task.result is not None:
        task.status = TaskStatus.COMPLETED


def discard_speculative(task: Task) -> None:
    """Discard speculative result; task will be re-run when deps are confirmed."""
    if task.speculative:
        task.status = TaskStatus.PENDING
        task.result = None
