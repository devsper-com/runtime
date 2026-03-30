from __future__ import annotations

from devsper.swarm.swarm import Swarm


class RunOrchestrator:
    """Facade for run orchestration to reduce direct coupling to Swarm internals."""

    def __init__(self, swarm: Swarm) -> None:
        self._swarm = swarm

    def run(self, user_task: str, hitl_resolver: object = None) -> dict[str, str]:
        return self._swarm.run(user_task=user_task, hitl_resolver=hitl_resolver)

