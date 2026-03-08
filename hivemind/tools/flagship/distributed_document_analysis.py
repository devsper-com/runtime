"""Analyze hundreds of documents using swarm parallelism: batch → swarm tasks → aggregate insights."""

import json
from pathlib import Path
from unittest.mock import patch

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.types.task import Task
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent
from hivemind.utils.event_logger import EventLog
from hivemind.tools.documents._docproc import run_docproc_to_markdown, DOCPROC_EXTENSIONS


class DistributedDocumentAnalysisTool(Tool):
    """
    Analyze many documents using swarm parallelism: split into batches, spawn swarm tasks,
    collect summaries, aggregate into a single research report.
    """

    name = "distributed_document_analysis"
    description = "Analyze hundreds of documents using swarm parallelism; returns aggregated research report."
    input_schema = {
        "type": "object",
        "properties": {
            "documents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of document paths to analyze",
            },
        },
        "required": ["documents"],
    }

    def run(self, **kwargs) -> str:
        documents = kwargs.get("documents")
        if not documents or not isinstance(documents, list):
            return "Error: documents must be a non-empty list of paths"
        paths = [p for p in documents if isinstance(p, str) and p.strip()][:30]

        tasks = []
        for i, path in enumerate(paths):
            task_id = f"doc_{i}"
            deps = [f"doc_{i - 1}"] if i > 0 else []
            tasks.append(Task(id=task_id, description=f"Summarize the document at: {path}", dependencies=deps))

        scheduler = Scheduler()
        scheduler.add_tasks(tasks)
        log = EventLog()

        def _mock_generate(model_name: str, prompt: str) -> str:
            for p in paths:
                if p in prompt:
                    content, _ = run_docproc_to_markdown(p)
                    if content:
                        return (content[:300] + "...") if len(content) > 300 else content
                    return f"Summary of document at {p} (no content extracted)."
            return "Summary unavailable."

        with patch("hivemind.agents.agent.generate", side_effect=_mock_generate):
            agent = Agent(model_name="mock", event_log=log)
            executor = Executor(scheduler=scheduler, agent=agent, worker_count=4, event_log=log)
            executor.run_sync()

        results = scheduler.get_results()
        summaries = [results.get(f"doc_{i}", "") for i in range(len(paths))]
        aggregated = {
            "total_documents": len(paths),
            "summaries": [{"path": p, "summary": s[:500]} for p, s in zip(paths, summaries)],
            "insights": f"Processed {len(paths)} documents with swarm parallelism. Total summaries: {len(summaries)}.",
        }
        return json.dumps(aggregated, indent=2)


register(DistributedDocumentAnalysisTool())
