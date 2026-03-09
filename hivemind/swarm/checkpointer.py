"""
Scheduler checkpointer: write snapshot to disk periodically for resume and node sync.

v1.9: Writes to {events_dir}/{run_id}.checkpoint.json. Atomic write. Restore for resume.
"""

import json
import os

from hivemind.swarm.scheduler import Scheduler
from hivemind.types.exceptions import CheckpointNotFoundError


class SchedulerCheckpointer:
    """Writes scheduler.snapshot() to disk periodically. Atomic write. Restore by run_id."""

    def __init__(
        self,
        events_dir: str = ".hivemind/events",
        interval_tasks: int = 10,
    ) -> None:
        self.events_dir = events_dir
        self.interval_tasks = interval_tasks
        self._completions_since_write = 0

    def _path(self, run_id: str) -> str:
        return os.path.join(self.events_dir, f"{run_id}.checkpoint.json")

    def _write_atomic(self, path: str, data: dict) -> None:
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
        os.replace(tmp, path)

    def on_task_completed(self, scheduler: Scheduler) -> None:
        """Call after each task completion; writes checkpoint every interval_tasks."""
        self._completions_since_write += 1
        if self._completions_since_write >= self.interval_tasks:
            self._completions_since_write = 0
            self.write_now(scheduler)

    def write_now(self, scheduler: Scheduler) -> None:
        """Write checkpoint once."""
        run_id = getattr(scheduler, "run_id", "")
        if not run_id:
            return
        path = self._path(run_id)
        self._write_atomic(path, scheduler.snapshot())

    def restore_latest(self, run_id: str) -> Scheduler | None:
        """Load checkpoint file; return restored Scheduler or None if not found."""
        path = self._path(run_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Scheduler.restore(data)

    def restore_or_raise(self, run_id: str) -> Scheduler:
        """Restore scheduler or raise CheckpointNotFoundError."""
        s = self.restore_latest(run_id)
        if s is None:
            raise CheckpointNotFoundError(f"No checkpoint found for run_id: {run_id!r}")
        return s
