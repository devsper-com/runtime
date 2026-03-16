"""Experiment strategy: DAG for experiments (setup -> run -> compare -> report)."""

import secrets

from devsper.types.task import Task

from devsper.intelligence.strategies.base import Strategy


def _short_id() -> str:
    return secrets.token_hex(4)


class ExperimentStrategy(Strategy):
    """Experiment pipeline: setup -> run -> compare -> report."""

    def plan(self, root_task: Task) -> list[Task]:
        steps = [
            ("setup", "Set up experiment parameters and environment."),
            ("run", "Run the experiment or parameter sweep."),
            ("compare", "Compare results and run statistical checks."),
            ("report", "Generate experiment report and recommendations."),
        ]
        task_ids: list[str] = []
        tasks: list[Task] = []
        for i, (_, desc) in enumerate(steps):
            tid = _short_id()
            task_ids.append(tid)
            deps = [task_ids[i - 1]] if i > 0 else []
            description = f"{root_task.description}\n\nStep: {desc}" if i == 0 else desc
            t = Task(id=tid, description=description, dependencies=deps)
            tasks.append(t)
        return tasks
