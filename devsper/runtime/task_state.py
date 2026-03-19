from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class TaskRunStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class DispatchableTask:
    task_id: str
    original_description: str
    enriched_description: str
    depends_on: tuple[str, ...]


class TaskStateMachine:
    """
    Pure state management for a single run.

    Owns:
    - authoritative status for each task_id
    - dependency graph indices (deps + reverse deps)
    - task_results for completed tasks

    It does not know about bus, workers, redis, or UI.
    """

    def __init__(self, tasks: Iterable[object]) -> None:
        tasks_list = list(tasks)
        self._original_description: dict[str, str] = {}
        self._additional_context: dict[str, str] = {}
        self._depends_on: dict[str, tuple[str, ...]] = {}
        self._dependents: dict[str, set[str]] = {}
        self._status: dict[str, TaskRunStatus] = {}
        self._task_results: dict[str, str] = {}
        self._assigned_worker: dict[str, str] = {}  # task_id -> worker_id (best-effort)

        for t in tasks_list:
            tid = getattr(t, "id", None)
            if not tid:
                continue
            desc = getattr(t, "description", "") or ""
            deps = getattr(t, "depends_on", None) or getattr(t, "dependencies", None) or []
            deps_t = tuple(str(d) for d in (deps or []))
            self._original_description[str(tid)] = str(desc)
            self._additional_context[str(tid)] = ""
            self._depends_on[str(tid)] = deps_t
            self._status[str(tid)] = TaskRunStatus.PENDING

        # Build reverse dependency index.
        for tid, deps in self._depends_on.items():
            for dep in deps:
                self._dependents.setdefault(dep, set()).add(tid)

        # Validate dependency references (do not crash: just mark invalid downstream as CANCELLED).
        unknown: set[str] = set()
        for tid, deps in self._depends_on.items():
            for dep in deps:
                if dep not in self._status:
                    unknown.add(f"{tid}->{dep}")
        if unknown:
            # Mark tasks with unknown deps as CANCELLED (they can never run).
            for edge in unknown:
                tid = edge.split("->", 1)[0]
                self._status[tid] = TaskRunStatus.CANCELLED

    @property
    def task_results(self) -> dict[str, str]:
        return dict(self._task_results)

    def status_of(self, task_id: str) -> TaskRunStatus | None:
        return self._status.get(task_id)

    def all_task_ids(self) -> list[str]:
        return list(self._status.keys())

    def get_ready_tasks(self) -> list[str]:
        """
        Return all task_ids currently READY.
        Also advances PENDING->READY for tasks whose dependencies are now COMPLETE.
        """
        for tid, st in list(self._status.items()):
            if st != TaskRunStatus.PENDING:
                continue
            deps = self._depends_on.get(tid, ())
            if all(self._status.get(d) == TaskRunStatus.COMPLETE for d in deps):
                self._transition(tid, TaskRunStatus.READY)
        return [tid for tid, st in self._status.items() if st == TaskRunStatus.READY]

    def build_dispatchable(self, task_id: str) -> DispatchableTask:
        original = self._original_description.get(task_id, "")
        deps = self._depends_on.get(task_id, ())
        ctx = self._additional_context.get(task_id, "") or ""
        enriched = self._enrich_description(original, ctx, deps)
        return DispatchableTask(
            task_id=task_id,
            original_description=original,
            enriched_description=enriched,
            depends_on=deps,
        )

    def append_context(self, task_id: str, text: str) -> None:
        """
        Append user-provided clarification (or other controller-injected context)
        that should be visible to the agent on (re)dispatch.
        """
        if not task_id or not text:
            return
        if task_id not in self._additional_context:
            return
        existing = self._additional_context.get(task_id, "") or ""
        self._additional_context[task_id] = (existing + str(text)).strip()

    def mark_dispatched(self, task_id: str, *, worker_id: str | None = None) -> None:
        self._transition(task_id, TaskRunStatus.DISPATCHED)
        if worker_id:
            self._assigned_worker[task_id] = worker_id

    def mark_running(self, task_id: str, *, worker_id: str | None = None) -> None:
        self._transition(task_id, TaskRunStatus.RUNNING)
        if worker_id:
            self._assigned_worker[task_id] = worker_id

    def mark_waiting(self, task_id: str) -> None:
        self._transition(task_id, TaskRunStatus.WAITING)

    def mark_complete(self, task_id: str, result: str) -> list[str]:
        self._task_results[task_id] = result or ""
        self._transition(task_id, TaskRunStatus.COMPLETE)
        return self._maybe_unblock_dependents(task_id)

    def mark_failed(self, task_id: str, error: str | None = None) -> list[str]:
        self._transition(task_id, TaskRunStatus.FAILED)
        # Cancel downstream tasks.
        cancelled: set[str] = set()
        stack = list(self._dependents.get(task_id, set()))
        while stack:
            tid = stack.pop()
            if tid in cancelled:
                continue
            cancelled.add(tid)
            self._transition(tid, TaskRunStatus.CANCELLED)
            stack.extend(self._dependents.get(tid, set()))
        return sorted(cancelled)

    def worker_timeout(self, worker_id: str) -> list[str]:
        """
        Transition tasks assigned to this worker back to READY (via PENDING gate),
        so the dispatcher can re-dispatch them.
        """
        requeued: list[str] = []
        for tid, wid in list(self._assigned_worker.items()):
            if wid != worker_id:
                continue
            st = self._status.get(tid)
            if st in (TaskRunStatus.RUNNING, TaskRunStatus.DISPATCHED, TaskRunStatus.WAITING):
                self._status[tid] = TaskRunStatus.PENDING
                requeued.append(tid)
        return requeued

    def requeue(self, task_id: str) -> None:
        """Best-effort requeue: move task back to PENDING so it can become READY again."""
        if not task_id or task_id not in self._status:
            return
        st = self._status.get(task_id)
        if st in (TaskRunStatus.COMPLETE, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED):
            return
        self._status[task_id] = TaskRunStatus.PENDING

    def is_run_complete(self) -> bool:
        # Terminal: COMPLETE / FAILED / CANCELLED
        for st in self._status.values():
            if st not in (TaskRunStatus.COMPLETE, TaskRunStatus.FAILED, TaskRunStatus.CANCELLED):
                return False
        return True

    def _maybe_unblock_dependents(self, completed_task_id: str) -> list[str]:
        newly_ready: list[str] = []
        for dep_tid in sorted(self._dependents.get(completed_task_id, set())):
            if self._status.get(dep_tid) != TaskRunStatus.PENDING:
                continue
            deps = self._depends_on.get(dep_tid, ())
            if all(self._status.get(d) == TaskRunStatus.COMPLETE for d in deps):
                self._transition(dep_tid, TaskRunStatus.READY)
                newly_ready.append(dep_tid)
        return newly_ready

    def _enrich_description(self, original: str, ctx: str, deps: tuple[str, ...]) -> str:
        enriched = (original or "").strip()
        if not deps:
            return (enriched + ("\n" + ctx.strip() if ctx.strip() else "")).strip()
        parts: list[str] = [enriched] if enriched else []
        if ctx.strip():
            parts.append("\n" + ctx.strip())
        for dep_id in deps:
            result = self._task_results.get(dep_id, "")
            if not result:
                continue
            truncated = result[:4000]
            parts.append(
                "\n\n=== Output from "
                + str(dep_id)[:8]
                + " ===\n"
                + truncated
                + ("\n" if not truncated.endswith("\n") else "")
                + "=== End ==="
            )
        return "".join(parts).strip()

    def _transition(self, task_id: str, new: TaskRunStatus) -> None:
        old = self._status.get(task_id)
        if old is None:
            return
        if old == new:
            return
        if not self._is_valid_transition(old, new):
            # Enforce "do not crash": ignore invalid transition.
            return
        self._status[task_id] = new

    def _is_valid_transition(self, old: TaskRunStatus, new: TaskRunStatus) -> bool:
        allowed: dict[TaskRunStatus, set[TaskRunStatus]] = {
            TaskRunStatus.PENDING: {TaskRunStatus.READY, TaskRunStatus.CANCELLED},
            TaskRunStatus.READY: {TaskRunStatus.DISPATCHED, TaskRunStatus.CANCELLED},
            TaskRunStatus.DISPATCHED: {TaskRunStatus.RUNNING, TaskRunStatus.READY, TaskRunStatus.CANCELLED},
            TaskRunStatus.RUNNING: {TaskRunStatus.WAITING, TaskRunStatus.COMPLETE, TaskRunStatus.FAILED, TaskRunStatus.READY},
            TaskRunStatus.WAITING: {TaskRunStatus.RUNNING, TaskRunStatus.READY, TaskRunStatus.CANCELLED},
            TaskRunStatus.COMPLETE: set(),
            TaskRunStatus.FAILED: set(),
            TaskRunStatus.CANCELLED: set(),
        }
        return new in allowed.get(old, set())

