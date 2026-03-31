from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from devsper.types.task import Task


@dataclass
class ExecutionNode:
    task_id: str
    status: str = "pending"
    attempts: int = 0
    parent_ids: tuple[str, ...] = ()
    child_ids: set[str] = field(default_factory=set)
    lineage_root: str | None = None
    worker_id: str | None = None
    assigned_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionGraph:
    """Mutable execution graph with lightweight lineage and retry tracking."""

    def __init__(self) -> None:
        self._nodes: dict[str, ExecutionNode] = {}

    def add_task(self, task: Task, lineage_root: str | None = None) -> None:
        parents = tuple(task.dependencies or [])
        node = self._nodes.get(task.id)
        if node is None:
            node = ExecutionNode(
                task_id=task.id,
                parent_ids=parents,
                lineage_root=lineage_root or task.id,
            )
            self._nodes[task.id] = node
        else:
            node.parent_ids = parents
            node.updated_at = datetime.now(timezone.utc)
        for pid in parents:
            parent = self._nodes.get(pid)
            if parent is None:
                parent = ExecutionNode(task_id=pid, lineage_root=lineage_root or pid)
                self._nodes[pid] = parent
            parent.child_ids.add(task.id)
            parent.updated_at = datetime.now(timezone.utc)

    def assign_worker(self, task_id: str, worker_id: str) -> None:
        node = self._nodes.get(task_id)
        if node is None:
            node = ExecutionNode(task_id=task_id, lineage_root=task_id)
            self._nodes[task_id] = node
        node.worker_id = worker_id
        node.assigned_at = datetime.now(timezone.utc)
        node.updated_at = datetime.now(timezone.utc)

    def mark_running(self, task_id: str, worker_id: str | None = None) -> None:
        node = self._nodes.get(task_id)
        if node is None:
            node = ExecutionNode(task_id=task_id, lineage_root=task_id)
            self._nodes[task_id] = node
        if worker_id:
            node.worker_id = worker_id
            node.assigned_at = datetime.now(timezone.utc)
        node.status = "running"
        node.attempts += 1
        node.updated_at = datetime.now(timezone.utc)

    def mark_completed(self, task_id: str) -> None:
        node = self._nodes.get(task_id)
        if node is None:
            return
        node.status = "completed"
        node.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, task_id: str) -> None:
        node = self._nodes.get(task_id)
        if node is None:
            return
        node.status = "failed"
        node.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for tid, n in self._nodes.items():
            out[tid] = {
                "task_id": n.task_id,
                "status": n.status,
                "attempts": n.attempts,
                "parent_ids": list(n.parent_ids),
                "child_ids": sorted(n.child_ids),
                "lineage_root": n.lineage_root,
                "worker_id": n.worker_id,
                "assigned_at": n.assigned_at.isoformat() if n.assigned_at else None,
                "created_at": n.created_at.isoformat(),
                "updated_at": n.updated_at.isoformat(),
            }
        return out

