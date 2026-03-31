from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re

from devsper.runtime.run_history import RunHistory
from devsper.types.event import Event

from devsper.export.model import (
    BundleExport,
    Citation,
    ClarificationQA,
    RunExport,
    TimelineItem,
)


_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV_RE = re.compile(r"\barXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\b", re.IGNORECASE)
_URL_RE = re.compile(r"\bhttps?://[^\s)>\]]+")


def _load_events(path: str) -> list[Event]:
    p = Path(path)
    if not p.is_file():
        return []
    out: list[Event] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Event.model_validate_json(line))
            except Exception:
                try:
                    out.append(Event.from_json(line))
                except Exception:
                    continue
    except Exception:
        return []
    out.sort(key=lambda e: e.timestamp)
    return out


def _candidate_events_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        from devsper.config import get_config

        cfg = get_config()
        d = Path(getattr(cfg, "events_dir", ".devsper/events")).expanduser()
        dirs.append(d)
    except Exception:
        pass
    cwd = Path.cwd()
    dirs.append(cwd / ".devsper" / "events")
    runtime_root = Path(__file__).resolve().parents[2]
    dirs.append(runtime_root / ".devsper" / "events")
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


def _resolve_events_path(run_id: str, events_path: str) -> str:
    p = Path(events_path).expanduser() if events_path else Path("")
    if events_path:
        if p.is_file():
            return str(p)
        # If path is relative, attempt to resolve against known project roots.
        if not p.is_absolute():
            for base in [Path.cwd(), Path(__file__).resolve().parents[2]]:
                cand = (base / p).resolve()
                if cand.is_file():
                    return str(cand)
    # Fallback: find by run_id stem in known events dirs.
    for d in _candidate_events_dirs():
        if not d.is_dir():
            continue
        cand = d / f"{run_id}.jsonl"
        if cand.is_file():
            return str(cand)
        for f in d.glob("*.jsonl"):
            if f.stem == run_id:
                return str(f)
    return ""


def _extract_citations(text: str) -> list[Citation]:
    if not text:
        return []
    citations: list[Citation] = []
    for doi in sorted(set(_DOI_RE.findall(text))):
        citations.append(Citation(key=f"doi-{len(citations)+1}", source="doi", doi=doi, title=doi))
    for arx in sorted(set(_ARXIV_RE.findall(text))):
        citations.append(
            Citation(
                key=f"arxiv-{len(citations)+1}",
                source="arxiv",
                arxiv_id=arx,
                title=f"arXiv:{arx}",
                url=f"https://arxiv.org/abs/{arx.split('v')[0]}",
            )
        )
    for url in sorted(set(_URL_RE.findall(text))):
        citations.append(Citation(key=f"url-{len(citations)+1}", source="url", url=url, title=url))
    return citations


def _build_run_export(row: object) -> RunExport:
    run_id = str(getattr(row, "run_id", "") or "")
    resolved_events_path = _resolve_events_path(
        run_id=run_id,
        events_path=str(getattr(row, "events_path", "") or ""),
    )
    events = _load_events(resolved_events_path)
    tool_counts: dict[str, int] = defaultdict(int)
    timeline: list[TimelineItem] = []
    task_outputs: dict[str, str] = {}
    task_output_chunks: dict[str, list[str]] = defaultdict(list)
    clar_needs: dict[str, tuple[str, str, str]] = {}  # req_id -> (task_id, question, ts)
    clarifications: list[ClarificationQA] = []
    all_text_fragments: list[str] = [
        getattr(row, "root_task", "") or "",
    ]

    for e in events:
        payload = e.payload or {}
        ev = e.type.value if hasattr(e.type, "value") else str(e.type)
        ts = e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp)
        task_id = str(payload.get("task_id") or "")
        msg = ""

        if ev == "tool_called":
            name = str(payload.get("tool") or payload.get("tool_name") or "tool")
            tool_counts[name] += 1
            preview = str(payload.get("result_preview") or "").strip()
            if task_id and preview:
                task_output_chunks[task_id].append(
                    f"[tool:{name}] {preview}"
                )
            msg = f"tool_called: {name}"
        elif ev == "task_completed":
            result = str(payload.get("result") or "")
            if task_id and result:
                task_outputs[task_id] = result
                all_text_fragments.append(result)
            msg = f"task_completed: {task_id[:8]}"
        elif ev == "task_failed":
            msg = f"task_failed: {task_id[:8]} {str(payload.get('error') or '')[:120]}".strip()
        elif ev == "clarification_needed":
            req_id = str(payload.get("request_id") or "")
            question = str(payload.get("question") or payload.get("context") or "").strip()
            if not question and isinstance(payload.get("fields"), list):
                fields = payload.get("fields") or []
                if fields and isinstance(fields[0], dict):
                    question = str(fields[0].get("question") or "")
            clar_needs[req_id] = (task_id, question, ts)
            msg = f"clarification_needed: {question[:90]}"
            all_text_fragments.append(question)
        elif ev == "clarification_received":
            req_id = str(payload.get("request_id") or "")
            answer = ""
            answers = payload.get("answers")
            if isinstance(answers, dict) and answers:
                answer = "; ".join(f"{k}: {v}" for k, v in answers.items())
            else:
                answer = str(payload.get("answer") or "")
            need = clar_needs.get(req_id)
            if need:
                clarifications.append(
                    ClarificationQA(
                        request_id=req_id,
                        task_id=need[0],
                        question=need[1],
                        answer=answer,
                        timestamp=ts,
                    )
                )
            msg = f"clarification_received: {answer[:90]}"
            all_text_fragments.append(answer)
        else:
            maybe_text = payload.get("context") or payload.get("message") or payload.get("description")
            if isinstance(maybe_text, str):
                all_text_fragments.append(maybe_text)
            msg = ev

        timeline.append(TimelineItem(timestamp=ts, event_type=ev, task_id=task_id, message=msg))

    # Backfill outputs using tool traces when direct task result payloads are absent.
    for tid, chunks in task_output_chunks.items():
        if tid in task_outputs:
            continue
        joined = "\n\n".join(chunks).strip()
        if joined:
            task_outputs[tid] = joined[:12000]

    all_citations = _extract_citations("\n".join(all_text_fragments))
    models_used: list[str] = []
    models_raw = getattr(row, "models_used", "[]")
    try:
        parsed = json.loads(models_raw) if isinstance(models_raw, str) else []
        if isinstance(parsed, list):
            models_used = [str(x) for x in parsed]
    except Exception:
        pass

    if not events:
        timeline.append(
            TimelineItem(
                timestamp="",
                event_type="export_note",
                task_id="",
                message="Event log not found for this run; exported metadata from run-history DB only.",
            )
        )

    return RunExport(
        run_id=run_id,
        root_task=str(getattr(row, "root_task", "") or ""),
        strategy=str(getattr(row, "strategy", "") or ""),
        started_at=str(getattr(row, "started_at", "") or ""),
        finished_at=str(getattr(row, "finished_at", "") or ""),
        duration_seconds=float(getattr(row, "duration_seconds", 0) or 0),
        total_tasks=int(getattr(row, "total_tasks", 0) or 0),
        completed_tasks=int(getattr(row, "completed_tasks", 0) or 0),
        failed_tasks=int(getattr(row, "failed_tasks", 0) or 0),
        estimated_cost_usd=getattr(row, "estimated_cost_usd", None),
        events_path=resolved_events_path or str(getattr(row, "events_path", "") or ""),
        model_names=models_used,
        tool_counts=dict(tool_counts),
        timeline=timeline,
        clarifications=clarifications,
        task_outputs=task_outputs,
        citations=all_citations,
    )


def collect_history_bundle(limit: int | None = None, db_path: str | None = None) -> BundleExport:
    history = RunHistory(Path(db_path).expanduser() if db_path else None)
    rows = history.list_runs(limit=limit or 100000)
    runs = [_build_run_export(r) for r in rows]
    global_citations: dict[str, Citation] = {}
    for run in runs:
        for c in run.citations:
            key = c.doi or c.arxiv_id or c.url or c.title
            if key and key not in global_citations:
                global_citations[key] = c
    return BundleExport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        run_count=len(runs),
        runs=runs,
        citations=list(global_citations.values()),
    )


def bundle_to_json_dict(bundle: BundleExport) -> dict:
    return {
        "generated_at": bundle.generated_at,
        "run_count": bundle.run_count,
        "runs": [asdict(r) for r in bundle.runs],
        "citations": [asdict(c) for c in bundle.citations],
    }
