"""Decision records per task for explainability."""

from dataclasses import dataclass, field


@dataclass
class ToolConsideration:
    tool_name: str
    similarity_score: float
    reliability_score: float
    blended_score: float
    selected: bool


@dataclass
class DecisionRecord:
    task_id: str
    task_description: str
    strategy_selected: str
    strategy_reason: str
    tools_considered: list[ToolConsideration] = field(default_factory=list)
    tools_selected: list[str] = field(default_factory=list)
    model_tier: str = ""
    model_selected: str = ""
    model_reason: str = ""
    memory_records_used: int = 0
    kg_context_injected: bool = False
    critic_score: float | None = None
    confidence: float = 0.0
    rationale: str = ""


class DecisionTreeBuilder:
    """Build DecisionRecords from events in a run."""

    def build_from_events(self, run_id: str, events_dir: str) -> list[DecisionRecord]:
        """Parse events from events_dir for this run_id and build one DecisionRecord per task."""
        import os
        import json
        from pathlib import Path
        records: list[DecisionRecord] = []
        path = Path(events_dir)
        if not path.is_dir():
            return records
        event_files = list(path.glob("*.jsonl"))
        if run_id:
            exact = path / f"{run_id}.jsonl"
            if exact.is_file():
                event_files = [exact]
            else:
                event_files = [f for f in event_files if run_id in f.stem or run_id in f.name]
        events: list[dict] = []
        for f in event_files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except Exception:
                            pass
            except Exception:
                pass
        task_ids = set()
        for ev in events:
            payload = ev.get("payload") or ev if isinstance(ev.get("payload"), dict) else {}
            tid = payload.get("task_id") or ev.get("task_id")
            if tid:
                task_ids.add(tid)
        for tid in sorted(task_ids):
            task_events = [e for e in events if (e.get("payload") or {}).get("task_id") == tid or e.get("task_id") == tid]
            model = ""
            tier = ""
            tools: list[str] = []
            for e in task_events:
                p = e.get("payload") or {}
                if e.get("type") == "task_model_selected" or p.get("model"):
                    model = p.get("model") or model
                    tier = p.get("tier") or tier
                if e.get("type") == "tool_called" or p.get("tool"):
                    t = p.get("tool")
                    if t and t not in tools:
                        tools.append(t)
            desc = next((p.get("description") for e in task_events for p in [e.get("payload") or {}] if p.get("description")), tid)
            rec = DecisionRecord(
                task_id=tid,
                task_description=desc or tid,
                strategy_selected=tier or "default",
                strategy_reason="from events",
                tools_considered=[],
                tools_selected=tools,
                model_tier=tier or "default",
                model_selected=model or "unknown",
                model_reason="from events",
                memory_records_used=0,
                kg_context_injected=False,
                critic_score=None,
                confidence=0.8,
                rationale=f"Task classified as {tier or 'default'}. Selected {len(tools)} tools ({', '.join(tools)}). Used {model or 'unknown'} ({tier or 'default'} tier). Confidence: 80%.",
            )
            records.append(rec)
        return records
