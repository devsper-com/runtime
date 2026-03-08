"""Execute a workflow: build tasks from steps, run via scheduler and executor."""

import secrets

from hivemind.types.task import Task

from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent
from hivemind.utils.event_logger import EventLog


def _short_id() -> str:
    return secrets.token_hex(4)


def run_workflow(
    steps: list[str],
    worker_model: str = "mock",
    worker_count: int = 2,
    event_log: EventLog | None = None,
    memory_router=None,
    use_tools: bool = False,
) -> dict[str, str]:
    """
    Run a workflow: steps are task descriptions in order (step i depends on step i-1).
    Returns task_id -> result.
    """
    if not steps:
        return {}
    event_log = event_log or EventLog()
    task_ids: list[str] = []
    tasks: list[Task] = []
    for i, step in enumerate(steps):
        tid = _short_id()
        task_ids.append(tid)
        deps = [task_ids[i - 1]] if i > 0 else []
        description = step if len(step) > 50 else f"Execute step: {step}"
        t = Task(id=tid, description=description, dependencies=deps)
        tasks.append(t)
    scheduler = Scheduler()
    scheduler.add_tasks(tasks)
    agent = Agent(
        model_name=worker_model,
        event_log=event_log,
        memory_router=memory_router,
        store_result_to_memory=False,
        use_tools=use_tools,
    )
    executor = Executor(
        scheduler=scheduler,
        agent=agent,
        worker_count=worker_count,
        event_log=event_log,
    )
    executor.run_sync()
    return scheduler.get_results()
