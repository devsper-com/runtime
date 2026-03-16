"""Code analysis strategy: DAG for repository analysis."""

import secrets

from devsper.types.task import Task

from devsper.intelligence.strategies.base import Strategy


def _short_id() -> str:
    return secrets.token_hex(4)


class CodeAnalysisStrategy(Strategy):
    """Code/repo pipeline: index -> structure -> dependencies -> report."""

    def plan(self, root_task: Task) -> list[Task]:
        steps = [
            ("index", "Index the codebase and identify main modules and entry points."),
            ("structure", "Analyze project structure and layout."),
            ("dependencies", "Map dependencies and external imports."),
            ("report", "Produce an architecture and code analysis report."),
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
