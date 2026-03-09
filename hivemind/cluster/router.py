"""Task routing with affinity: memory, tool cache, load."""

from hivemind.cluster.node_info import NodeInfo
from hivemind.types.task import Task


def _parse_version(version: str) -> tuple[int, int]:
    """Return (major, minor) from version string like 1.10 or 1.9.0."""
    parts = version.replace("-", ".").split(".")
    try:
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        major, minor = 0, 0
    return (major, minor)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class TaskRouter:
    """Route ready tasks to the best available worker. Scoring: memory_affinity, tool_affinity, load_score."""

    # Weights
    MEMORY_WEIGHT = 0.35
    TOOL_WEIGHT = 0.25
    LOAD_WEIGHT = 0.40

    def __init__(self, controller_version: str = "1.9.0") -> None:
        self._controller_version = controller_version
        self._ctrl_major, self._ctrl_minor = _parse_version(controller_version)

    def route(
        self,
        task: Task,
        workers: list[NodeInfo],
        worker_stats: dict[str, dict],
    ) -> NodeInfo | None:
        """Score all workers; return highest-scored; None if none available or version incompatible."""
        if not workers:
            return None
        best: tuple[float, NodeInfo] = (-1.0, workers[0])
        for w in workers:
            if not self._version_compatible(w):
                continue
            score = self._score(task, w, worker_stats.get(w.node_id, {}))
            if score > best[0]:
                best = (score, w)
        return best[1] if best[0] >= 0 else None

    def _version_compatible(self, worker: NodeInfo) -> bool:
        maj, min_ = _parse_version(worker.version)
        return (maj == self._ctrl_major and min_ == self._ctrl_minor)

    def _score(
        self,
        task: Task,
        worker: NodeInfo,
        stats: dict,
    ) -> float:
        memory_affinity = self._memory_affinity(task, stats)
        tool_affinity = self._tool_affinity(task, stats)
        load_score = self._load_score(worker, stats)
        return (
            memory_affinity * self.MEMORY_WEIGHT
            + tool_affinity * self.TOOL_WEIGHT
            + load_score * self.LOAD_WEIGHT
        )

    def _memory_affinity(self, task: Task, stats: dict) -> float:
        deps = list(task.dependencies or [])
        if not deps:
            return 0.0
        completed_here = list(stats.get("completed_task_ids", []))
        hit = sum(1 for d in deps if d in completed_here)
        return hit / len(deps)

    def _tool_affinity(self, task: Task, stats: dict) -> float:
        tools_needed = self._tools_for_task(task)
        if not tools_needed:
            return 0.0
        cached = set(stats.get("cached_tools", []))
        hit = sum(1 for t in tools_needed if t in cached)
        return hit / len(tools_needed)

    def _tools_for_task(self, task: Task) -> list[str]:
        try:
            from hivemind.tools.selector import get_tools_for_task
            from hivemind.tools.scoring import get_default_score_store
            score_store = get_default_score_store()
        except Exception:
            score_store = None
        try:
            tools = get_tools_for_task(
                task.description or "",
                role=getattr(task, "role", None),
                score_store=score_store,
            )
            return [t.name for t in tools]
        except Exception:
            return []

    def _load_score(self, worker: NodeInfo, stats: dict) -> float:
        active = int(stats.get("active_tasks", 0))
        avg_duration = float(stats.get("avg_task_duration_seconds", 0.0))
        max_workers = worker.max_workers or 1
        weighted_load = active * avg_duration
        load_ratio = weighted_load / (max_workers * 60.0)
        return 1.0 - _clamp(load_ratio, 0.0, 1.0)
