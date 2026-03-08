"""Data science strategy: DAG for dataset workflow."""

import secrets

from hivemind.types.task import Task

from hivemind.intelligence.strategies.base import Strategy


def _short_id() -> str:
    return secrets.token_hex(4)


class DataScienceStrategy(Strategy):
    """Data science pipeline: load -> profile -> analyze -> visualize."""

    def plan(self, root_task: Task) -> list[Task]:
        steps = [
            ("load", "Load and validate the dataset."),
            ("profile", "Generate data profile and basic statistics."),
            ("analyze", "Run analysis and identify patterns or models."),
            ("visualize", "Create visualizations and summary reports."),
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
