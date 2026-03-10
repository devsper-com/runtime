"""
Swarm: entrypoint for users. Orchestrates planner → scheduler → executor → results.

User code:
    swarm = Swarm(worker_count=4)
    result = swarm.run("Analyze diffusion model research")
    # Or with config file:
    swarm = Swarm(config="hivemind.toml")
    result = swarm.run("analyze diffusion models")
"""

import asyncio
import json
import os
import threading
from pathlib import Path
from datetime import datetime, timezone

from hivemind.types.task import Task
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import resolve_model

from hivemind.swarm.planner import Planner
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent


def _fake_config():
    """Minimal config for single-node when no config file loaded."""
    class N:
        mode = "single"
    class C:
        events_dir = ".hivemind/events"
        nodes = N()
    return C()


def _persist_dag(scheduler: Scheduler, event_log: EventLog) -> None:
    """Write task DAG to events dir as {run_id}_dag.json for graph export."""
    run_id = getattr(event_log, "run_id", None)
    if not run_id:
        return
    log_path = getattr(event_log, "log_path", None)
    if not log_path:
        return
    events_dir = os.path.dirname(log_path)
    nodes = [
        {"id": t.id, "description": (t.description or "")[:200]}
        for t in scheduler._tasks.values()
    ]
    edges = list(scheduler._graph.edges())
    path = os.path.join(events_dir, f"{run_id}_dag.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, indent=0)


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
            self.worker_count = (
                worker_count
                if worker_count is not None
                else getattr(cfg.swarm, "workers", 4)
            )
            worker_raw = worker_model if worker_model is not None else cfg.models.worker
            planner_raw = (
                planner_model if planner_model is not None else cfg.models.planner
            )
            self.worker_model = resolve_model(worker_raw, "analysis")
            self.planner_model = resolve_model(planner_raw, "planning")
            self.adaptive = (
                adaptive
                if adaptive is not None
                else getattr(cfg.swarm, "adaptive_planning", False)
                or getattr(cfg.swarm, "adaptive_execution", False)
            )
            self.use_tools = use_tools if use_tools is not None else True
            self.speculative_execution = getattr(
                cfg.swarm, "speculative_execution", False
            )
            self.cache_enabled = getattr(cfg.swarm, "cache_enabled", False)
            self.parallel_tools = getattr(cfg.swarm, "parallel_tools", True)
            self.message_bus_enabled = getattr(cfg.swarm, "message_bus_enabled", True)
            self.prefetch_enabled = getattr(cfg.swarm, "prefetch_enabled", True)
            self._config = cfg
            # v1.10.5: register MCP server tools from config
            mcp_servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
            for server_config in mcp_servers:
                try:
                    from hivemind.tools.mcp import register_mcp_server
                    register_mcp_server(server_config)
                except Exception:
                    pass  # don't fail Swarm init if MCP server unreachable
            # v1.10.5: register A2A agent tools from config (auto_discover)
            a2a_agents = getattr(getattr(cfg, "a2a", None), "agents", None) or []
            for agent_config in a2a_agents:
                if not getattr(agent_config, "auto_discover", True):
                    continue
                try:
                    from hivemind.agents.a2a.discovery import register_a2a_agent
                    register_a2a_agent(agent_config)
                except Exception:
                    pass
        else:
            self.worker_count = worker_count if worker_count is not None else 4
            worker_raw = worker_model if worker_model is not None else "mock"
            planner_raw = planner_model if planner_model is not None else "mock"
            self.worker_model = resolve_model(worker_raw, "analysis")
            self.planner_model = resolve_model(planner_raw, "planning")
            self.adaptive = adaptive if adaptive is not None else False
            self.use_tools = use_tools if use_tools is not None else False
            self.speculative_execution = False
            self.cache_enabled = False
            self.parallel_tools = True
            self.message_bus_enabled = True
            self.prefetch_enabled = True
            self._config = None
        self.event_log = event_log or EventLog()
        self.memory_router = memory_router
        self.store_swarm_memory = store_swarm_memory
        self._last_scheduler: Scheduler | None = None
        self._last_reasoning_store = None
        self._pause_event = threading.Event()
        self._pause_event.set()

    def pause(self) -> None:
        """Pause the executor: currently-running tasks finish, no new tasks start."""
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume the executor so new tasks can be picked."""
        self._pause_event.set()

    def run(self, user_task: str) -> dict[str, str]:
        """
        Create root task → plan subtasks → add to scheduler → run executor → return task_id → result.
        """
        self._emit(events.SWARM_STARTED, {"user_task": user_task[:200]})

        root = Task(id="root", description=user_task, dependencies=[])
        from hivemind.intelligence.strategy_selector import StrategySelector
        from hivemind.intelligence.strategies import get_strategy_for

        knowledge_graph = None
        if self._config is not None:
            kg_cfg = getattr(self._config, "knowledge", None)
            if kg_cfg and (getattr(kg_cfg, "guide_planning", False) or getattr(kg_cfg, "auto_extract", False)):
                from hivemind.knowledge.knowledge_graph import KnowledgeGraph
                from hivemind.memory.memory_store import get_default_store
                knowledge_graph = KnowledgeGraph(store=get_default_store())
                knowledge_graph.load()
                knowledge_graph.build_from_memory(merge=True)
        selector = StrategySelector()
        selected = selector.select(root)
        strategy_instance = get_strategy_for(selected)
        prompt_suffix = selector.suggest_planner_prompt_suffix(selected)
        guide_planning = False
        min_confidence = 0.30
        if self._config is not None and getattr(self._config, "knowledge", None):
            guide_planning = getattr(self._config.knowledge, "guide_planning", False)
            min_confidence = getattr(self._config.knowledge, "min_confidence", 0.30)
        planner = Planner(
            model_name=self.planner_model,
            event_log=self.event_log,
            strategy=strategy_instance,
            prompt_suffix=prompt_suffix,
            knowledge_graph=knowledge_graph,
            guide_planning=guide_planning,
            min_confidence=min_confidence,
        )
        subtasks = planner.plan(root)

        scheduler = Scheduler()
        scheduler.add_tasks(subtasks)
        scheduler.run_id = getattr(self.event_log, "run_id", "") or ""
        _persist_dag(scheduler, self.event_log)

        from hivemind.reasoning.store import ReasoningStore
        from hivemind.agents.message_bus import SwarmMessageBus

        message_bus = None
        if getattr(self, "message_bus_enabled", True):
            message_bus = SwarmMessageBus(event_log=self.event_log)

        nodes_mode = "distributed"  # no config -> use executor path (v1.9 behavior)
        if self._config is not None:
            nodes_cfg = getattr(self._config, "nodes", None)
            nodes_mode = getattr(nodes_cfg, "mode", "single") if nodes_cfg else "single"
        if nodes_mode == "single" and self._config is not None:
            def _agent_factory(cfg):
                rs = ReasoningStore()
                mb = SwarmMessageBus(event_log=self.event_log) if getattr(self, "message_bus_enabled", True) else None
                return Agent(
                    model_name=self.worker_model,
                    event_log=self.event_log,
                    memory_router=self.memory_router,
                    store_result_to_memory=False,
                    use_tools=self.use_tools,
                    reasoning_store=rs,
                    user_task=user_task,
                    parallel_tools=getattr(self, "parallel_tools", True),
                    message_bus=mb,
                )
            from hivemind.nodes.single import create_single_node
            single_node = create_single_node(
                config=self._config or _fake_config(),
                scheduler=scheduler,
                event_log=self.event_log,
                memory_router=self.memory_router,
                agent_factory=_agent_factory,
                user_task=user_task,
                message_bus=message_bus,
            )
            async def _run_single():
                await single_node.start()
                return await single_node.run_until_finished()
            results = asyncio.run(_run_single())
            self._last_scheduler = scheduler
            self._last_reasoning_store = None
            if self.store_swarm_memory and self.memory_router and results:
                self._store_swarm_memory(user_task, scheduler)
            self._emit(events.SWARM_FINISHED, {"task_count": len(results)})
            try:
                from hivemind.intelligence.analysis.run_report import build_report_from_events
                from hivemind.runtime.run_history import RunHistory
                log_path = getattr(self.event_log, "log_path", None)
                if log_path:
                    events_dir = os.path.dirname(log_path)
                    run_id = getattr(self.event_log, "run_id", None)
                    if run_id:
                        report = build_report_from_events(run_id, events_dir)
                        RunHistory().record_run(report)
                        if self._config and getattr(getattr(self._config, "knowledge", None), "auto_extract", False):
                            from hivemind.knowledge.knowledge_graph import KnowledgeGraph
                            from hivemind.knowledge.extractor import KnowledgeExtractor
                            from hivemind.memory.memory_store import get_default_store
                            kg = KnowledgeGraph(store=get_default_store())
                            kg.load()
                            kg.build_from_memory(merge=True)
                            completed_tasks = self.last_completed_tasks
                            min_conf = getattr(self._config.knowledge, "min_confidence", 0.60)
                            extractor = KnowledgeExtractor(min_confidence=min_conf)
                            try:
                                asyncio.get_event_loop().run_until_complete(
                                    extractor.extract_from_run(
                                        run_id, completed_tasks, kg, event_log=self.event_log
                                    )
                                )
                            except Exception:
                                loop = asyncio.new_event_loop()
                                loop.run_until_complete(
                                    extractor.extract_from_run(
                                        run_id, completed_tasks, kg, event_log=self.event_log
                                    )
                                )
            except Exception:
                pass
            return results

        reasoning_store = ReasoningStore()
        agent = Agent(
            model_name=self.worker_model,
            event_log=self.event_log,
            memory_router=self.memory_router,
            store_result_to_memory=False,
            use_tools=self.use_tools,
            reasoning_store=reasoning_store,
            user_task=user_task,
            parallel_tools=getattr(self, "parallel_tools", True),
            message_bus=message_bus,
        )
        task_cache = None
        semantic_cache = None
        if getattr(self, "cache_enabled", False):
            from hivemind.cache import TaskCache

            task_cache = TaskCache()
            cfg = getattr(self, "_config", None)
            if cfg and getattr(getattr(cfg, "cache", None), "semantic", False):
                from hivemind.cache.task_cache import SemanticTaskCache

                cache_cfg = cfg.cache
                semantic_cache = SemanticTaskCache(
                    similarity_threshold=getattr(cache_cfg, "similarity_threshold", 0.92),
                    max_age_hours=getattr(cache_cfg, "max_age_hours", 168.0),
                )
        complexity_router = None
        models_config = None
        if self._config is not None:
            from hivemind.providers.complexity_router import TaskComplexityRouter

            complexity_router = TaskComplexityRouter()
            models_config = self._config.models

        critic_agent = None
        critic_enabled = False
        critic_roles: list[str] = []
        fast_model = self.worker_model
        if self._config is not None:
            critic_enabled = getattr(self._config.swarm, "critic_enabled", False)
            critic_roles = list(
                getattr(self._config.swarm, "critic_roles", [])
                or ["research", "analysis", "code"]
            )
            fast_model = getattr(self._config.models, "fast", None) or self.worker_model
            if critic_enabled:
                from hivemind.agents.critic import CriticAgent
                critic_agent = CriticAgent(event_log=self.event_log)

        prefetcher = None
        if getattr(self, "speculative_execution", False) and getattr(
            self, "prefetch_enabled", True
        ):
            from hivemind.swarm.prefetcher import TaskPrefetcher
            from hivemind.tools.selector import get_tools_for_task
            try:
                from hivemind.tools.scoring import get_default_score_store
                score_store = get_default_score_store()
            except Exception:
                score_store = None
            prefetch_max_age = 30.0
            if self._config is not None:
                prefetch_max_age = getattr(
                    self._config.swarm, "prefetch_max_age_seconds", 30.0
                )
            prefetcher = TaskPrefetcher(
                memory_router=self.memory_router,
                tool_selector=lambda desc, role=None, score_store=None: get_tools_for_task(
                    desc or "", role=role, score_store=score_store
                ),
                score_store=score_store,
                max_age_seconds=prefetch_max_age,
            )

        bus = None
        checkpointer = None
        if self._config is not None:
            try:
                from hivemind.bus import get_bus
                bus = get_bus(self._config)
            except Exception:
                pass
            if getattr(getattr(self._config, "swarm", None), "checkpoint_enabled", True):
                from hivemind.swarm.checkpointer import SchedulerCheckpointer
                checkpointer = SchedulerCheckpointer(
                    events_dir=getattr(self._config, "events_dir", ".hivemind/events"),
                    interval_tasks=getattr(
                        getattr(self._config, "swarm", None), "checkpoint_interval", 10
                    ),
                )

        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=self.worker_count,
            event_log=self.event_log,
            planner=planner if self.adaptive else None,
            adaptive=self.adaptive,
            speculative_execution=getattr(self, "speculative_execution", False),
            task_cache=task_cache,
            pause_event=self._pause_event,
            semantic_cache=semantic_cache,
            complexity_router=complexity_router,
            models_config=models_config,
            streaming_dag=True,
            critic_agent=critic_agent,
            critic_enabled=critic_enabled,
            critic_roles=critic_roles,
            fast_model=fast_model,
            prefetcher=prefetcher,
            bus=bus,
            checkpointer=checkpointer,
        )
        executor.run_sync()

        self._last_scheduler = scheduler
        self._last_reasoning_store = reasoning_store
        results = scheduler.get_results()
        if self.store_swarm_memory and self.memory_router and results:
            self._store_swarm_memory(user_task, scheduler)
        self._emit(events.SWARM_FINISHED, {"task_count": len(results)})
        try:
            from hivemind.intelligence.analysis.run_report import build_report_from_events
            from hivemind.runtime.run_history import RunHistory
            log_path = getattr(self.event_log, "log_path", None)
            if log_path:
                events_dir = os.path.dirname(log_path)
                run_id = getattr(self.event_log, "run_id", None)
                if run_id:
                    report = build_report_from_events(run_id, events_dir)
                    RunHistory().record_run(report)
                    if self._config and getattr(getattr(self._config, "knowledge", None), "auto_extract", False):
                        from hivemind.knowledge.knowledge_graph import KnowledgeGraph
                        from hivemind.knowledge.extractor import KnowledgeExtractor
                        from hivemind.memory.memory_store import get_default_store
                        kg = KnowledgeGraph(store=get_default_store())
                        kg.load()
                        kg.build_from_memory(merge=True)
                        completed_tasks = self.last_completed_tasks
                        min_conf = getattr(self._config.knowledge, "min_confidence", 0.60)
                        extractor = KnowledgeExtractor(min_confidence=min_conf)
                        try:
                            asyncio.get_event_loop().run_until_complete(
                                extractor.extract_from_run(
                                    run_id, completed_tasks, kg, event_log=self.event_log
                                )
                            )
                        except Exception:
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(
                                extractor.extract_from_run(
                                    run_id, completed_tasks, kg, event_log=self.event_log
                                )
                            )
        except Exception:
            pass
        return results

    @property
    def last_completed_tasks(self) -> list[Task]:
        """After run(), return completed tasks (id, description, result) for report building."""
        if self._last_scheduler is None:
            return []
        return self._last_scheduler.get_completed_tasks()

    def map_reduce(
        self, dataset: list, map_fn, reduce_fn, worker_count: int | None = None
    ):
        """
        First-class map-reduce: run map_fn on each item in parallel, then reduce_fn on results.
        Uses the same worker pool pattern as the executor.
        """
        from hivemind.swarm.map_reduce import map_reduce as _map_reduce

        workers = worker_count if worker_count is not None else self.worker_count
        return _map_reduce(dataset, map_fn, reduce_fn, worker_count=workers)

    def _store_swarm_memory(self, user_task: str, scheduler: Scheduler) -> None:
        """Store important outputs (research findings, summaries, results) into memory after run."""
        from hivemind.memory.memory_store import (
            MemoryStore,
            get_default_store,
            generate_memory_id,
        )
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
            run_id = getattr(self.event_log, "run_id", "") or ""
            record = MemoryRecord(
                id=generate_memory_id(),
                memory_type=mt,
                source_task=task.id,
                content=content[:15000],
                tags=["swarm", "task", task.id, user_task[:100]],
                run_id=run_id,
            )
            record = index.ensure_embedding(record)
            store.store(record)

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(
                timestamp=datetime.now(timezone.utc), type=event_type, payload=payload
            )
        )
