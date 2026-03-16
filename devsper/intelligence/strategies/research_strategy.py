"""Research strategy: DAG for literature review (corpus -> topic -> citation -> review)."""

import secrets

from devsper.types.task import Task

from devsper.intelligence.strategies.base import Strategy


def _short_id() -> str:
    return secrets.token_hex(4)


class ResearchStrategy(Strategy):
    """Research pipeline: corpus_builder -> topic_extraction -> citation_graph -> literature_review."""

    def plan(self, root_task: Task) -> list[Task]:
        steps = [
            ("corpus_builder", "Build a corpus of relevant papers and sources for the topic."),
            ("topic_extraction", "Extract main topics and themes from the corpus."),
            ("citation_graph", "Build citation graph and identify key references."),
            ("literature_review", "Write a structured literature review synthesizing findings."),
        ]
        task_ids: list[str] = []
        tasks: list[Task] = []
        for i, (step_id, desc) in enumerate(steps):
            tid = _short_id()
            task_ids.append(tid)
            deps = [task_ids[i - 1]] if i > 0 else []
            # Include root context in first step
            description = f"{root_task.description}\n\nStep: {desc}" if i == 0 else desc
            t = Task(id=tid, description=description, dependencies=deps)
            tasks.append(t)
        return tasks
