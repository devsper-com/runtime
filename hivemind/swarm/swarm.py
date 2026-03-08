"""
Swarm: entrypoint for users. Orchestrates planner → scheduler → executor → results.

User code:
    swarm = Swarm(worker_count=4)
    result = swarm.run("Analyze diffusion model research")
    # Or with config file:
    swarm = Swarm(config="hivemind.toml")
    result = swarm.run("analyze diffusion models")
"""

from pathlib import Path
from datetime import datetime, timezone

from hivemind.types.task import Task
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog

from hivemind.swarm.planner import Planner
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent


class Swarm:
    """Orchestrates planner, scheduler, executor, and agent. Single entrypoint for running a task."""

    def __init__(
        self,
        worker_count: int | None = None,
        worker_model: str | None = None,
        planner_model: str | None = None,
        event_log: EventLog | None = None,
        adaptive: bool | None = None,
        memory_router=None,
        store_swarm_memory: bool = True,
        use_tools: bool | None = None,
        config: str | Path | object | None = None,
    ) -> None:
        # Load from config file or config object if provided
        cfg = None
        if config is not None:
            if isinstance(config, (str, Path)):
                from hivemind.config import get_config
                cfg = get_config(config_path=str(config))
            else:
                cfg = config
        if cfg is not None:
            self.worker_count = worker_count if worker_count is not None else getattr(cfg.swarm, "workers", 4)
            self.worker_model = worker_model if worker_model is not None else cfg.models.worker
            self.planner_model = planner_model if planner_model is not None else cfg.models.planner
            self.adaptive = adaptive if adaptive is not None else getattr(cfg.swarm, "adaptive_planning", False)
            self.use_tools = use_tools if use_tools is not None else True
        else:
            self.worker_count = worker_count if worker_count is not None else 4
            self.worker_model = worker_model if worker_model is not None else "mock"
            self.planner_model = planner_model if planner_model is not None else "mock"
            self.adaptive = adaptive if adaptive is not None else False
            self.use_tools = use_tools if use_tools is not None else False
        self.event_log = event_log or EventLog()
        self.memory_router = memory_router
        self.store_swarm_memory = store_swarm_memory
        self._last_scheduler: Scheduler | None = None

    def run(self, user_task: str) -> dict[str, str]:
        """
        Create root task → plan subtasks → add to scheduler → run executor → return task_id → result.
        """
        self._emit(events.SWARM_STARTED, {"user_task": user_task[:200]})

        root = Task(id="root", description=user_task, dependencies=[])
        from hivemind.intelligence.strategy_selector import StrategySelector
        from hivemind.intelligence.strategies import get_strategy_for

        selector = StrategySelector()
        selected = selector.select(root)
        strategy_instance = get_strategy_for(selected)
        prompt_suffix = selector.suggest_planner_prompt_suffix(selected)
        planner = Planner(
            model_name=self.planner_model,
            event_log=self.event_log,
            strategy=strategy_instance,
            prompt_suffix=prompt_suffix,
        )
        subtasks = planner.plan(root)

        scheduler = Scheduler()
        scheduler.add_tasks(subtasks)

        agent = Agent(
            model_name=self.worker_model,
            event_log=self.event_log,
            memory_router=self.memory_router,
            store_result_to_memory=False,
            use_tools=self.use_tools,
        )
        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=self.worker_count,
            event_log=self.event_log,
            planner=planner if self.adaptive else None,
            adaptive=self.adaptive,
        )
        executor.run_sync()

        self._last_scheduler = scheduler
        results = scheduler.get_results()
        if self.store_swarm_memory and self.memory_router and results:
            self._store_swarm_memory(user_task, scheduler)
        self._emit(events.SWARM_FINISHED, {"task_count": len(results)})
        return results

    @property
    def last_completed_tasks(self) -> list[Task]:
        """After run(), return completed tasks (id, description, result) for report building."""
        if self._last_scheduler is None:
            return []
        return self._last_scheduler.get_completed_tasks()

    def map_reduce(self, dataset: list, map_fn, reduce_fn, worker_count: int | None = None):
        """
        First-class map-reduce: run map_fn on each item in parallel, then reduce_fn on results.
        Uses the same worker pool pattern as the executor.
        """
        from hivemind.swarm.map_reduce import map_reduce as _map_reduce
        workers = worker_count if worker_count is not None else self.worker_count
        return _map_reduce(dataset, map_fn, reduce_fn, worker_count=workers)

    def _store_swarm_memory(self, user_task: str, scheduler: Scheduler) -> None:
        """Store important outputs (research findings, summaries, results) into memory after run."""
        from hivemind.memory.memory_store import MemoryStore, get_default_store, generate_memory_id
        from hivemind.memory.memory_types import MemoryRecord, MemoryType
        from hivemind.memory.memory_index import MemoryIndex

        store = getattr(self.memory_router, "store", None)
        if not isinstance(store, MemoryStore):
            store = get_default_store()
        index = getattr(self.memory_router, "index", None) or MemoryIndex(store)
        for task in scheduler.get_completed_tasks():
            content = (task.result or "").strip()
            if not content or len(content) < 10:
                continue
            desc = (task.description or "").lower()
            if "research" in desc or "paper" in desc or "literature" in desc:
                mt = MemoryType.RESEARCH
            elif "code" in desc or "codebase" in desc or "analyze" in desc:
                mt = MemoryType.ARTIFACT
            elif "data" in desc or "dataset" in desc or "experiment" in desc:
                mt = MemoryType.SEMANTIC
            else:
                mt = MemoryType.EPISODIC
            record = MemoryRecord(
                id=generate_memory_id(),
                memory_type=mt,
                source_task=task.id,
                content=content[:15000],
                tags=["swarm", "task", task.id, user_task[:100]],
            )
            record = index.ensure_embedding(record)
            store.store(record)

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
