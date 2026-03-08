"""
Task optimizer: merge redundant tasks, detect parallel opportunities, remove unnecessary tasks.
"""

import re
from hivemind.types.task import Task


def _normalize_for_sim(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())


class TaskOptimizer:
    """
    Optimize a task graph: merge redundant tasks, identify tasks that can run in parallel,
    drop no-op or duplicate steps.
    """

    def __init__(self, min_similarity_chars: int = 20) -> None:
        self.min_similarity_chars = min_similarity_chars

    def optimize(self, tasks: list[Task]) -> list[Task]:
        """
        Return a new list of tasks with redundancies merged, dependencies updated,
        and optional parallelization hints. Does not mutate input tasks.
        """
        if not tasks:
            return []
        seen_norm: dict[str, Task] = {}
        for t in tasks:
            norm = _normalize_for_sim(t.description)[:200]
            if norm in seen_norm and len(norm) >= self.min_similarity_chars:
                continue
            seen_norm[norm] = t
        deduped = list(seen_norm.values())
        merged = self._merge_trivial(deduped)
        return self._rebuild_deps(merged)

    def _merge_trivial(self, tasks: list[Task]) -> list[Task]:
        out: list[Task] = []
        for t in tasks:
            desc = (t.description or "").strip()
            if len(desc) < 15 and out:
                prev = out[-1]
                out[-1] = Task(
                    id=prev.id,
                    description=prev.description + "; " + desc,
                    dependencies=prev.dependencies,
                )
            else:
                out.append(t)
        return out

    def _rebuild_deps(self, tasks: list[Task]) -> list[Task]:
        """Rebuild task list with sequential ids and deps (task_1 -> task_2 -> ...)."""
        id_map = {t.id: i for i, t in enumerate(tasks, start=1)}
        result: list[Task] = []
        for i, t in enumerate(tasks, start=1):
            new_id = f"task_{i}"
            deps = [f"task_{id_map[d]}" for d in t.dependencies if d in id_map]
            if not deps and i > 1:
                deps = [f"task_{i - 1}"]
            result.append(
                Task(id=new_id, description=t.description, dependencies=deps)
            )
        return result

    def detect_parallel_opportunities(self, tasks: list[Task]) -> list[list[str]]:
        """
        Return groups of task ids that could run in parallel (same dependencies).
        Each group is a list of task ids that all depend on the same set and could be run together.
        """
        by_dep_key: dict[tuple, list[str]] = {}
        for t in tasks:
            key = tuple(sorted(t.dependencies))
            by_dep_key.setdefault(key, []).append(t.id)
        return [ids for ids in by_dep_key.values() if len(ids) > 1]

    def remove_unnecessary(self, tasks: list[Task], predicate=None) -> list[Task]:
        """
        Remove tasks for which predicate(task) is True (e.g. no-op descriptions).
        predicate defaults to: description too short or placeholder-like.
        """
        if predicate is None:
            def predicate(t: Task) -> bool:
                d = (t.description or "").strip().lower()
                if len(d) < 5:
                    return True
                if d in ("n/a", "none", "todo", "tbd", "-", "..."):
                    return True
                return False
        return [t for t in tasks if not predicate(t)]
