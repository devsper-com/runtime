"""Wrap LangChain runnables and agent pipelines as Devsper tasks (minimal surface, no extra framework)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from devsper.types.task import Task, TaskStatus

LANGCHAIN_TASK_PREFIX = "[devsper:langchain]"


def langchain_task(
    task_id: str,
    *,
    description: str = "",
    dependencies: list[str] | None = None,
    role: str | None = None,
) -> Task:
    """Return a Devsper `Task` tagged for LangChain execution (visible in logs and DAG exports)."""
    desc = (description or "").strip() or f"LangChain runnable ({task_id})"
    if LANGCHAIN_TASK_PREFIX not in desc:
        desc = f"{LANGCHAIN_TASK_PREFIX} {desc}"
    return Task(
        id=task_id,
        description=desc,
        dependencies=list(dependencies or []),
        status=TaskStatus.PENDING,
        role=role,
    )


def stringify_langchain_output(value: Any, *, max_len: int = 32000) -> str:
    """Normalize LangChain/LangGraph outputs to a string suitable for `Task.result`."""
    if value is None:
        return ""
    if hasattr(value, "content"):
        text = getattr(value, "content", value)
        return str(text)[:max_len]
    if isinstance(value, dict):
        if "output" in value:
            return stringify_langchain_output(value["output"], max_len=max_len)
        if "messages" in value:
            parts: list[str] = []
            for m in value["messages"]:
                if hasattr(m, "content"):
                    parts.append(str(getattr(m, "content", m)))
                else:
                    parts.append(str(m))
            return "\n".join(parts).strip()[:max_len]
        try:
            return json.dumps(value, default=str)[:max_len]
        except TypeError:
            return str(value)[:max_len]
    if isinstance(value, str):
        return value[:max_len]
    return str(value)[:max_len]


async def run_langchain_runnable(
    task: Task,
    runnable: Any,
    input_data: dict[str, Any] | str | list[Any],
    *,
    config: Any | None = None,
) -> str:
    """
    Run a LangChain `Runnable`, agent, or legacy executor with async `ainvoke` when available.

    `input_data` may be a string (wrapped as `{"input": ...}`), a message list (chat models), or a dict.
    """
    inp: Any = input_data
    if isinstance(inp, str):
        inp = {"input": inp}
    if hasattr(runnable, "ainvoke"):
        out = await runnable.ainvoke(inp, config=config)
    else:
        out = await asyncio.to_thread(runnable.invoke, inp, config)
    return stringify_langchain_output(out)
