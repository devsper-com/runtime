"""
MetaPlanner: decomposes mega-tasks into sub-swarms with dependencies, SLAs, and priorities.
Coordinates execution across sub-swarms and monitors SLA breaches.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from devsper.utils.models import generate


@dataclass
class SLAConfig:
    max_duration_seconds: int
    max_cost_usd: float | None = None
    min_quality_score: float | None = None  # from critic scores
    on_breach: Literal["cancel", "escalate", "continue"] = "continue"


@dataclass
class SubSwarmSpec:
    swarm_id: str
    root_task: str
    priority: int  # 1 (highest) to 10 (lowest)
    sla: SLAConfig
    worker_count: int
    model_override: str | None = None
    depends_on: list[str] = field(default_factory=list)  # other swarm_ids


@dataclass
class SLABreach:
    swarm_id: str
    breach_type: Literal["duration", "cost", "quality"]
    limit: float
    actual: float
    action_taken: str


@dataclass
class MetaRunResult:
    mega_task: str
    sub_swarm_results: dict[str, dict]  # swarm_id -> results
    total_duration_seconds: float
    total_cost_usd: float | None
    sla_breaches: list[SLABreach]
    final_synthesis: str


def _validate_specs(specs: list[SubSwarmSpec]) -> None:
    """Raise ValueError if priority out of range or depends_on has cycles."""
    ids_ = {s.swarm_id for s in specs}
    for s in specs:
        if not (1 <= s.priority <= 10):
            raise ValueError(f"SubSwarmSpec {s.swarm_id}: priority must be 1-10, got {s.priority}")
        for dep in s.depends_on:
            if dep not in ids_:
                raise ValueError(f"SubSwarmSpec {s.swarm_id}: depends_on {dep!r} not in swarm ids")
    # Cycle detection
    graph: dict[str, list[str]] = {s.swarm_id: list(s.depends_on) for s in specs}
    path = set()
    visited = set()

    def visit(n: str) -> None:
        if n in path:
            raise ValueError(f"Cycle in depends_on involving {n!r}")
        if n in visited:
            return
        path.add(n)
        for c in graph.get(n, []):
            visit(c)
        path.remove(n)
        visited.add(n)

    for n in graph:
        if n not in visited:
            visit(n)


def _topological_order(specs: list[SubSwarmSpec]) -> list[SubSwarmSpec]:
    """Return specs in dependency order (dependencies first)."""
    by_id = {s.swarm_id: s for s in specs}
    in_degree = {s.swarm_id: 0 for s in specs}
    for s in specs:
        for dep in s.depends_on:
            in_degree[s.swarm_id] += 1
    from collections import deque
    q: list[str] = [i for i, d in in_degree.items() if d == 0]
    order: list[str] = []
    while q:
        n = q.pop(0)
        order.append(n)
        for s in specs:
            if n in s.depends_on:
                in_degree[s.swarm_id] -= 1
                if in_degree[s.swarm_id] == 0:
                    q.append(s.swarm_id)
    if len(order) != len(specs):
        order = [s.swarm_id for s in sorted(specs, key=lambda x: (x.priority, x.swarm_id))]
    return [by_id[i] for i in order if i in by_id]


class MetaPlanner:
    """Decomposes mega-tasks into sub-swarms and runs them with SLA monitoring."""

    def __init__(self, model_name: str = "mock", max_swarms: int = 20) -> None:
        self.model_name = model_name
        self.max_swarms = max_swarms

    async def decompose(self, mega_task: str) -> list[SubSwarmSpec]:
        """LLM call: given mega_task, produce JSON list of SubSwarmSpecs. Validates no cycles and priority 1-10."""
        prompt = f"""You are a meta-planner. Given the following mega-task, decompose it into independent or dependent sub-tasks, each to be run as a separate swarm.

Mega-task: {mega_task}

Respond with a JSON array of objects. Each object must have:
- swarm_id: string (short id, e.g. "research", "code", "review")
- root_task: string (the task this swarm will execute)
- priority: int (1 = highest, 10 = lowest)
- sla: object with max_duration_seconds (int), max_cost_usd (number or null), min_quality_score (number 0-1 or null), on_breach ("cancel"|"escalate"|"continue")
- worker_count: int (1-8)
- model_override: string or null
- depends_on: array of swarm_ids that must complete before this one (can be empty)

Ensure no circular dependencies. Return only the JSON array, no markdown."""

        out = await asyncio.to_thread(generate, self.model_name, prompt)
        text = (out or "").strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json") or part.startswith("["):
                    text = part[4:].strip() if part.startswith("json") else part
                    break
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = []
        if not isinstance(raw, list):
            raw = []
        specs: list[SubSwarmSpec] = []
        for i, item in enumerate(raw[: self.max_swarms]):
            if not isinstance(item, dict):
                continue
            sla = item.get("sla") or {}
            sla_config = SLAConfig(
                max_duration_seconds=int(sla.get("max_duration_seconds", 300)),
                max_cost_usd=float(sla["max_cost_usd"]) if sla.get("max_cost_usd") is not None else None,
                min_quality_score=float(sla["min_quality_score"]) if sla.get("min_quality_score") is not None else None,
                on_breach=(sla.get("on_breach") or "continue").lower()[:8],
            )
            if sla_config.on_breach not in ("cancel", "escalate", "continue"):
                sla_config.on_breach = "continue"
            spec = SubSwarmSpec(
                swarm_id=str(item.get("swarm_id", f"swarm_{i}")),
                root_task=str(item.get("root_task", mega_task)),
                priority=int(item.get("priority", 5)),
                sla=sla_config,
                worker_count=max(1, min(8, int(item.get("worker_count", 2)))),
                model_override=str(item["model_override"]) if item.get("model_override") else None,
                depends_on=[str(d) for d in item.get("depends_on") or []],
            )
            specs.append(spec)
        _validate_specs(specs)
        return specs

    async def run(self, mega_task: str, max_swarms: int | None = None, budget_usd: float | None = None) -> MetaRunResult:
        """Decompose -> build DAG -> run sub-swarms in order; monitor SLAs; return aggregated result with synthesis."""
        max_n = max_swarms or self.max_swarms
        specs = await self.decompose(mega_task)
        specs = specs[:max_n]
        ordered = _topological_order(specs)
        sub_swarm_results: dict[str, dict] = {}
        sla_breaches: list[SLABreach] = []
        total_cost: float | None = None
        start = datetime.now(timezone.utc)

        from devsper.swarm.swarm import Swarm
        from devsper.config import get_config
        from devsper.utils.event_logger import EventLog

        cfg = get_config()
        event_log = EventLog(events_folder_path=cfg.events_dir)

        for spec in ordered:
            swarm_start = datetime.now(timezone.utc)
            swarm = Swarm(
                worker_count=spec.worker_count,
                worker_model=spec.model_override or cfg.models.worker,
                planner_model=cfg.models.planner,
                event_log=event_log,
                config=cfg,
            )
            try:
                result = swarm.run(spec.root_task)
            except Exception as e:
                result = {"error": str(e)}
            elapsed = (datetime.now(timezone.utc) - swarm_start).total_seconds()
            sub_swarm_results[spec.swarm_id] = result

            if elapsed > spec.sla.max_duration_seconds:
                breach = SLABreach(
                    swarm_id=spec.swarm_id,
                    breach_type="duration",
                    limit=float(spec.sla.max_duration_seconds),
                    actual=elapsed,
                    action_taken=spec.sla.on_breach,
                )
                sla_breaches.append(breach)
                if spec.sla.on_breach == "cancel":
                    break

        total_duration_seconds = (datetime.now(timezone.utc) - start).total_seconds()

        # Final synthesis via LLM
        results_summary = json.dumps({k: (v if isinstance(v, dict) else {"result": str(v)}) for k, v in sub_swarm_results.items()}, indent=0)[:6000]
        synth_prompt = f"""Mega-task: {mega_task}

Sub-swarm results summary:
{results_summary}

SLA breaches (if any): {[f"{b.swarm_id}: {b.breach_type}" for b in sla_breaches]}

Write a short final synthesis (2-4 sentences) summarizing the overall outcome and any caveats."""

        synth_out = await asyncio.to_thread(generate, self.model_name, synth_prompt)
        final_synthesis = (synth_out or "").strip() or "No synthesis generated."

        return MetaRunResult(
            mega_task=mega_task,
            sub_swarm_results=sub_swarm_results,
            total_duration_seconds=total_duration_seconds,
            total_cost_usd=total_cost,
            sla_breaches=sla_breaches,
            final_synthesis=final_synthesis,
        )
