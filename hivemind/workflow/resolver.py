"""Resolve step dependencies into execution order (waves)."""

from collections import deque

from hivemind.workflow.schema import WorkflowStep


class WorkflowCycleError(Exception):
    """Raised when depends_on forms a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Dependency cycle: {' -> '.join(cycle)}")


def build_execution_order(steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
    """
    Topological sort of steps using depends_on edges.
    Returns list of "waves"; steps in the same wave can run in parallel.
    Steps with no depends_on are in wave 0.
    Raises WorkflowCycleError with the cycle path if a cycle is detected.
    """
    step_map = {s.id: s for s in steps}
    # in_degree[s] = number of dependencies of s (steps s waits for)
    in_degree = {s.id: len(s.depends_on) for s in steps}
    # dependants[dep] = list of step ids that depend on dep
    dependants: dict[str, list[str]] = {s.id: [] for s in steps}
    for s in steps:
        for dep in s.depends_on:
            dependants[dep].append(s.id)

    waves: list[list[WorkflowStep]] = []
    queue: deque[str] = deque(sid for sid, d in in_degree.items() if d == 0)
    remaining = set(step_map.keys())

    while queue:
        wave_ids: list[str] = list(queue)
        queue.clear()
        for sid in wave_ids:
            remaining.discard(sid)
            for nxt in dependants[sid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)
        waves.append([step_map[sid] for sid in wave_ids])

    if remaining:
        # Cycle: find one
        cycle = _find_cycle(steps)
        raise WorkflowCycleError(cycle)

    return waves


def _find_cycle(steps: list[WorkflowStep]) -> list[str]:
    """Return one cycle as list of step ids."""
    step_map = {s.id: s for s in steps}
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()
    cycle_start: str | None = None

    def dfs(sid: str) -> bool:
        nonlocal cycle_start
        visited.add(sid)
        path.append(sid)
        path_set.add(sid)
        step = step_map.get(sid)
        if step:
            for dep in step.depends_on:
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in path_set:
                    cycle_start = dep
                    return True
        path.pop()
        path_set.discard(sid)
        return False

    for sid in step_map:
        if sid not in visited and dfs(sid):
            # Build cycle from path: from cycle_start to end of path
            try:
                idx = path.index(cycle_start)
                return path[idx:] + [cycle_start]
            except (ValueError, TypeError):
                return path + [path[0]] if path else list(step_map.keys())[:1]

    return list(step_map.keys())[:1]


def validate_dag(steps: list[WorkflowStep]) -> list[str]:
    """Return list of error strings (used by validator)."""
    errors: list[str] = []
    step_ids = {s.id for s in steps}

    for s in steps:
        for dep in s.depends_on:
            if dep not in step_ids:
                errors.append(f"Step {s.id!r} depends_on unknown step {dep!r}")

    if not errors:
        try:
            build_execution_order(steps)
        except WorkflowCycleError as e:
            errors.append(str(e))

    return errors
