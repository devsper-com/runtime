"""Map LangGraph compiled graphs to Devsper task DAGs and run nodes with bounded concurrency."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from devsper.swarm.scheduler import Scheduler
from devsper.types.task import Task, TaskStatus

log = logging.getLogger(__name__)

_SKIP = frozenset({"__start__", "__end__"})


def default_list_merge_state(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """
    Merge a node patch into accumulated graph state.

    For keys present in both sides with list values, lists are concatenated (typical for `MessagesState`).
    Otherwise values from `patch` replace.
    """
    out = dict(state)
    for k, v in patch.items():
        if k in out and isinstance(out[k], list) and isinstance(v, list):
            out[k] = list(out[k]) + list(v)
        else:
            out[k] = v
    return out


def _patch_summary(patch: dict[str, Any], *, max_len: int = 2000) -> str:
    try:
        return json.dumps(patch, default=str)[:max_len]
    except TypeError:
        return str(patch)[:max_len]


def compiled_graph_to_tasks(compiled: Any, *, description_fmt: str | None = None) -> list[Task]:
    """
    Build a list of Devsper `Task` objects from a compiled LangGraph graph's static topology.

    Task ids match LangGraph node names. Dependencies follow edges, ignoring `__start__` / `__end__`.
    Raises if the topology is not a DAG (same validation as `Scheduler.add_tasks`).
    """
    try:
        G = compiled.get_graph()
    except Exception as exc:
        raise TypeError("object must be a compiled LangGraph graph with get_graph()") from exc
    fmt = description_fmt or "LangGraph node `{name}`"
    predecessors: dict[str, list[str]] = {}
    for edge in G.edges:
        predecessors.setdefault(edge.target, []).append(edge.source)
    tasks: list[Task] = []
    for name in G.nodes:
        if name in _SKIP:
            continue
        preds = [p for p in predecessors.get(name, []) if p not in _SKIP]
        desc = fmt.format(name=name)
        tasks.append(
            Task(
                id=str(name),
                description=desc,
                dependencies=list(preds),
                status=TaskStatus.PENDING,
            )
        )
    if not tasks:
        raise ValueError("no executable LangGraph nodes found (excluding __start__/__end__)")
    probe = Scheduler()
    probe.add_tasks(tasks)
    return tasks


async def run_compiled_graph_as_devsper_tasks(
    compiled: Any,
    initial_state: dict[str, Any],
    *,
    worker_count: int = 4,
    state_merge: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    on_node_complete: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None = None,
) -> dict[str, Any]:
    """
    Execute a compiled LangGraph using Devsper's task DAG semantics: each node is one schedulable unit.

    Ready nodes (dependencies satisfied) run concurrently up to `worker_count`. Shared graph state is
    updated under a lock so parallel branches merge safely; use a custom `state_merge` if your
    schema needs different rules than `default_list_merge_state`.
    """
    merge = state_merge or default_list_merge_state
    nodes_map = getattr(compiled, "nodes", None)
    if not isinstance(nodes_map, dict):
        raise TypeError("compiled graph has no nodes mapping")

    tasks = compiled_graph_to_tasks(compiled)
    scheduler = Scheduler()
    scheduler.add_tasks(tasks)

    state: dict[str, Any] = dict(initial_state)
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, int(worker_count)))
    failures: list[BaseException] = []

    async def run_one(task: Task) -> None:
        name = task.id
        node = nodes_map.get(name)
        if node is None:
            async with lock:
                scheduler.mark_failed(name, f"no Pregel node for {name!r}")
            failures.append(KeyError(name))
            return
        try:
            async with sem:
                async with lock:
                    snapshot = dict(state)
                patch = await node.ainvoke(snapshot)
                if not isinstance(patch, dict):
                    patch = {"output": patch}
                async with lock:
                    merged = merge(state, patch)
                    state.clear()
                    state.update(merged)
                    scheduler.mark_completed(name, _patch_summary(patch))
            if on_node_complete is not None:
                async with lock:
                    snap = dict(state)
                await on_node_complete(name, snap)
        except Exception as exc:  # noqa: BLE001 — surface as task failure + aggregate
            log.exception("langgraph node %s failed", name)
            async with lock:
                scheduler.mark_failed(name, f"{type(exc).__name__}: {exc}")
            failures.append(exc)

    while not scheduler.is_finished():
        if any(t.status == TaskStatus.FAILED for t in scheduler.get_all_tasks()):
            for t in scheduler.get_all_tasks():
                if t.status == TaskStatus.PENDING:
                    scheduler.mark_failed(t.id, "aborted: upstream LangGraph node failure")
            break
        ready = scheduler.get_ready_tasks()
        if not ready:
            await asyncio.sleep(0.01)
            continue
        await asyncio.gather(*(run_one(t) for t in ready))

    if failures:
        raise failures[0]
    return dict(state)
