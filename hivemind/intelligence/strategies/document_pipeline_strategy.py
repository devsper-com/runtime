"""Document pipeline strategy: DAG for document processing."""

import secrets

from hivemind.types.task import Task

from hivemind.intelligence.strategies.base import Strategy


def _short_id() -> str:
    return secrets.token_hex(4)


class DocumentPipelineStrategy(Strategy):
    """Document pipeline: ingest -> extract -> link -> report."""

    def plan(self, root_task: Task) -> list[Task]:
        steps = [
            ("ingest", "Ingest documents and extract raw text/metadata."),
            ("extract", "Extract entities, topics, and structure from documents."),
            ("link", "Link entities and build cross-document references."),
            ("report", "Produce a document intelligence report."),
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
