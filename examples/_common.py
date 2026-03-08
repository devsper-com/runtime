"""
Common helpers for examples: ensure tools are loaded, output dir, progress logging.
"""

import json
import os
from pathlib import Path

import hivemind.tools  # noqa: F401

from hivemind.memory.memory_index import MemoryIndex
from hivemind.memory.memory_router import MemoryRouter
from hivemind.memory.memory_store import MemoryStore, get_default_store, generate_memory_id
from hivemind.memory.memory_types import MemoryRecord, MemoryType
from hivemind.tools.tool_runner import run_tool


def examples_output_dir() -> Path:
    """Directory for example outputs (JSON/md)."""
    out = Path(__file__).resolve().parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def log(msg: str) -> None:
    print(f"[hivemind] {msg}")


def run_tool_safe(name: str, args: dict) -> str:
    """Run a tool and return result; log progress."""
    log(f"Tool: {name} {list(args.keys())}")
    out = run_tool(name, args)
    log(f"  -> {len(out)} chars")
    return out


def store_in_memory(content: str, memory_type: str = "semantic", tags: list | None = None) -> None:
    """Store a string in the default memory store for swarm context."""
    store = get_default_store()
    index = MemoryIndex(store)
    mt = MemoryType.SEMANTIC if memory_type == "semantic" else MemoryType.RESEARCH
    record = MemoryRecord(
        id=generate_memory_id(),
        memory_type=mt,
        source_task="example",
        content=content[:15000],
        tags=tags or ["example"],
    )
    record = index.ensure_embedding(record)
    store.store(record)


def get_memory_router() -> MemoryRouter:
    """Default memory router (store + index) for swarm."""
    store = get_default_store()
    index = MemoryIndex(store)
    return MemoryRouter(store=store, index=index, top_k=5)


def normalize_report_text(text: str) -> str:
    """Normalize markdown/report text: fix line endings, collapse excess newlines, strip trailing whitespace."""
    if not text or not text.strip():
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        out.append(line)
        prev_blank = is_blank
    result = "\n".join(out)
    if result and not result.endswith("\n"):
        result += "\n"
    return result


def _normalize_meta_value(v: object) -> object:
    """Normalize values for meta JSON: strings get newlines collapsed to space."""
    if isinstance(v, str):
        return v.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
    if isinstance(v, dict):
        return {k: _normalize_meta_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalize_meta_value(x) for x in v]
    return v


def save_json(data: dict, filename: str, normalize_strings: bool = False) -> Path:
    """Save dict as JSON. If normalize_strings is True, collapse newlines in string values (for meta JSON)."""
    out = examples_output_dir() / filename
    to_dump = _normalize_meta_value(data) if normalize_strings else data
    with open(out, "w", encoding="utf-8") as f:
        json.dump(to_dump, f, indent=2)
    log(f"Saved: {out}")
    return out


def build_report_from_swarm(swarm: object, title: str) -> str:
    """Build markdown report from swarm.last_completed_tasks: section heading = task description, body = result."""
    tasks = getattr(swarm, "last_completed_tasks", None) or []
    if not tasks:
        return f"# {title}\n\n(No completed tasks.)\n"
    parts = [f"# {title}\n"]
    for t in tasks:
        desc = (getattr(t, "description", None) or t.id or "Task").strip()
        result = (getattr(t, "result", None) or "").strip()
        parts.append(f"## {desc}\n\n{result}")
    return "\n\n".join(parts)


def save_markdown(text: str, filename: str) -> Path:
    out = examples_output_dir() / filename
    normalized = normalize_report_text(text)
    out.write_text(normalized, encoding="utf-8")
    log(f"Saved: {out}")
    return out
