from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Citation:
    key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    source: str = ""
    url: str = ""
    doi: str = ""
    arxiv_id: str = ""


@dataclass
class ClarificationQA:
    request_id: str
    task_id: str
    question: str
    answer: str
    timestamp: str = ""


@dataclass
class TimelineItem:
    timestamp: str
    event_type: str
    task_id: str = ""
    message: str = ""


@dataclass
class RunExport:
    run_id: str
    root_task: str
    strategy: str
    started_at: str
    finished_at: str
    duration_seconds: float
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    estimated_cost_usd: float | None
    events_path: str
    model_names: list[str] = field(default_factory=list)
    tool_counts: dict[str, int] = field(default_factory=dict)
    timeline: list[TimelineItem] = field(default_factory=list)
    clarifications: list[ClarificationQA] = field(default_factory=list)
    task_outputs: dict[str, str] = field(default_factory=dict)
    citations: list[Citation] = field(default_factory=list)


@dataclass
class BundleExport:
    generated_at: str
    run_count: int
    runs: list[RunExport]
    citations: list[Citation] = field(default_factory=list)
