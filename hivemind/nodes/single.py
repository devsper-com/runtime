"""
Single-node mode: one process runs controller + worker with InMemoryBus and filesystem state.
Zero-config, no Redis. Behaviorally identical to pre-v1.10 Swarm.
"""

import asyncio
import logging
from pathlib import Path

from hivemind.types.task import Task
from hivemind.bus.backends.memory import InMemoryBus
from hivemind.cluster.state_backend import FilesystemStateBackend
from hivemind.cluster.local import InMemoryRegistry, LocalLeaderElector
from hivemind.cluster.router import TaskRouter
from hivemind.swarm.scheduler import Scheduler

log = logging.getLogger(__name__)


class SingleNode:
    """Controller + worker in one process; InMemoryBus; no RPC, no Redis."""

    def __init__(
        self,
        config: object,
        scheduler: Scheduler,
        bus: object,
        state_backend: object,
        registry: object,
        elector: object,
        router: TaskRouter,
        controller_node: object,
        worker_node: object,
        event_log: object,
    ) -> None:
        self.config = config
        self.scheduler = scheduler
        self.bus = bus
        self.state_backend = state_backend
        self.registry = registry
        self.elector = elector
        self.router = router
        self.controller_node = controller_node
        self.worker_node = worker_node
        self.event_log = event_log
        self.run_id = getattr(scheduler, "run_id", "") or ""

    async def start(self) -> None:
        await self.bus.start()
        await asyncio.gather(
            self.controller_node.start(),
            self.worker_node.start(),
        )

    async def run_until_finished(self) -> dict[str, str]:
        """Wait until scheduler is finished; return results."""
        # Yield so the event loop runs elector.watch -> _become_leader -> dispatch_loop
        await asyncio.sleep(0.3)
        while not self.scheduler.is_finished():
            await asyncio.sleep(0.05)
        return self.scheduler.get_results()


def create_single_node(
    config: object,
    scheduler: Scheduler,
    event_log: object,
    memory_router: object,
    agent_factory: object,
    user_task: str = "",
    message_bus: object = None,
) -> SingleNode:
    """Build SingleNode with InMemoryBus, filesystem state, in-memory registry/elector."""
    run_id = getattr(scheduler, "run_id", "") or ""
    bus = InMemoryBus()
    events_dir = getattr(config, "events_dir", ".hivemind/events")
    state_backend = FilesystemStateBackend(events_dir)
    registry = InMemoryRegistry(run_id)
    elector = LocalLeaderElector(run_id)
    try:
        import hivemind
        version = getattr(hivemind, "__version__", "1.10.0")
    except Exception:
        version = "1.10.0"
    router = TaskRouter(controller_version=version)
    from hivemind.nodes.controller import ControllerNode
    from hivemind.nodes.worker import WorkerNode
    try:
        from hivemind.tools.selector import get_tools_for_task
        tool_selector = lambda desc, role=None, score_store=None: get_tools_for_task(
            desc or "", role=role, score_store=score_store
        )
    except Exception:
        tool_selector = lambda desc, role=None, score_store=None: []
    try:
        from hivemind.tools.scoring import get_default_score_store
        score_store = get_default_score_store()
    except Exception:
        score_store = None
    prefetcher = None
    try:
        from hivemind.swarm.prefetcher import TaskPrefetcher
        prefetcher = TaskPrefetcher(
            memory_router=memory_router,
            tool_selector=tool_selector,
            score_store=score_store,
            max_age_seconds=30.0,
        )
    except Exception:
        pass
    controller = ControllerNode(
        config=config,
        scheduler=scheduler,
        bus=bus,
        state_backend=state_backend,
        registry=registry,
        elector=elector,
        router=router,
        event_log=event_log,
    )
    worker = WorkerNode(
        config=config,
        bus=bus,
        registry=registry,
        memory_router=memory_router,
        tool_selector=tool_selector,
        score_store=score_store,
        prefetcher=prefetcher,
        agent_factory=agent_factory,
        event_log=event_log,
        run_id=run_id,
        user_task=user_task,
        message_bus=message_bus,
    )
    return SingleNode(
        config=config,
        scheduler=scheduler,
        bus=bus,
        state_backend=state_backend,
        registry=registry,
        elector=elector,
        router=router,
        controller_node=controller,
        worker_node=worker,
        event_log=event_log,
    )


def _make_node_id() -> str:
    from uuid import uuid4
    return str(uuid4())
