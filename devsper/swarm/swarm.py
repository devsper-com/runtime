"""
Swarm: entrypoint for users. Orchestrates planner → scheduler → executor → results.

User code:
    swarm = Swarm(worker_count=4)
    result = swarm.run("Analyze diffusion model research")
    # Or with config file:
    swarm = Swarm(config="devsper.toml")
    result = swarm.run("analyze diffusion models")
"""

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)

from devsper.types.task import Task
from devsper.types.event import Event, events
from devsper.utils.event_logger import EventLog
from devsper.utils.models import resolve_model

from devsper.swarm.planner import Planner
from devsper.swarm.scheduler import Scheduler
from devsper.runtime.executor import Executor
from devsper.agents.agent import Agent
from devsper.agents.registry import AgentRegistry
from devsper.budget import BudgetManager
from devsper.telemetry import instrument_swarm_run, record_exception
from devsper.telemetry.trulens import (
    init_trulens,
    get_session,
    make_recorder,
    instrument as _tru_instrument,
)


def _fake_config():
    """Minimal config for single-node when no config file loaded."""
    class N:
        mode = "single"
    class C:
        events_dir = ".devsper/events"
        nodes = N()
    return C()


def _persist_dag(scheduler: Scheduler, event_log: EventLog, execution_graph: object | None = None) -> None:
    """Write task DAG to events dir as {run_id}_dag.json for graph export."""
    run_id = getattr(event_log, "run_id", None)
    if not run_id:
        return
    log_path = getattr(event_log, "log_path", None)
    if not log_path:
        return
    events_dir = os.path.dirname(log_path)
    ex_map: dict = {}
    if execution_graph is not None and hasattr(execution_graph, "to_dict"):
        ex_map = execution_graph.to_dict() or {}

    nodes = []
    for t in scheduler._tasks.values():
        extra = ex_map.get(t.id) or {}
        desc = extra.get("description") if extra.get("description") else (t.description or "")
        agent = extra.get("agent_name") or getattr(t, "role", None) or "agent"
        worker = extra.get("worker_id")
        status = extra.get("status") or "pending"
        deps = extra.get("dependencies") or list(t.dependencies or [])
        nodes.append(
            {
                "id": t.id,
                "description": (desc or "")[:2000],
                "agent_name": agent,
                "agent": agent,
                "worker_id": worker,
                "worker": worker,
                "status": status,
                "dependencies": deps,
            }
        )
    edges = list(scheduler._graph.edges())
    path = os.path.join(events_dir, f"{run_id}_dag.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, indent=0)


class _TruSwarmApp:
    """Thin TruLens-instrumented wrapper for swarm execution.

    TruLens @instrument marks this method so every call is captured as a record
    when a TruCustomApp recorder is active.  The Swarm delegates to this wrapper
    only when TruLens is enabled; otherwise _run_core() is called directly.
    """

    def __init__(self, swarm: "Swarm") -> None:
        self._swarm = swarm

    @_tru_instrument
    def execute(self, user_task: str, hitl_resolver: object = None) -> dict:
        return self._swarm._run_core(user_task, hitl_resolver)


class RunResult(dict):
    """Backward-compatible run result map with optional metadata."""

    budget: dict | None = None


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
        clarification_queue: object = None,
        budget_usd: float | None = None,
        budget_on_exceeded: str | None = None,
    ) -> None:
        self.clarification_queue = clarification_queue
        self._current_executor = None
        # Load from config file or config object if provided
        cfg = None
        if config is not None:
            if isinstance(config, (str, Path)):
                from devsper.config import get_config

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
            # Ensure node layer (WorkerNode) uses the same effective model overrides.
            try:
                if worker_model is not None:
                    cfg.models.worker = worker_raw
                if planner_model is not None:
                    cfg.models.planner = planner_raw
            except Exception:
                pass
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
            self.budget_usd = (
                float(budget_usd)
                if budget_usd is not None
                else float(getattr(getattr(cfg, "budget", None), "limit_usd", 0.0))
            )
            self.budget_on_exceeded = (
                str(budget_on_exceeded)
                if budget_on_exceeded is not None
                else str(getattr(getattr(cfg, "budget", None), "on_exceeded", "warn"))
            )
            # v1.10.5: register MCP server tools from config
            mcp_servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
            for server_config in mcp_servers:
                try:
                    from devsper.tools.mcp import register_mcp_server
                    register_mcp_server(server_config)
                except Exception:
                    pass  # don't fail Swarm init if MCP server unreachable
            # v1.10.5: register A2A agent tools from config (auto_discover)
            a2a_agents = getattr(getattr(cfg, "a2a", None), "agents", None) or []
            for agent_config in a2a_agents:
                if not getattr(agent_config, "auto_discover", True):
                    continue
                try:
                    from devsper.agents.a2a.discovery import register_a2a_agent
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
            self.budget_usd = float(budget_usd or 0.0)
            self.budget_on_exceeded = str(budget_on_exceeded or "warn")
        self.event_log = event_log or EventLog()
        self.memory_router = memory_router
        self.store_swarm_memory = store_swarm_memory
        self._last_scheduler: Scheduler | None = None
        self._last_reasoning_store = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        # Initialize TruLens session if enabled in config
        _tele = getattr(cfg, "telemetry", None) if cfg is not None else None
        if getattr(_tele, "trulens_enabled", True):
            try:
                from devsper import __version__

                init_trulens(
                    database_url=str(getattr(_tele, "trulens_database_url", "") or ""),
                    app_version=__version__,
                )
            except Exception as _tlu_exc:
                log.warning("TruLens init skipped: %s", _tlu_exc)

    def pause(self) -> None:
        """Pause the executor: currently-running tasks finish, no new tasks start."""
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume the executor so new tasks can be picked."""
        self._pause_event.set()

    def _trulens_enabled(self) -> bool:
        """Return True if TruLens recording is configured and a session exists."""
        tele = getattr(self._config, "telemetry", None)
        enabled = bool(getattr(tele, "trulens_enabled", True)) if tele else True
        return enabled and get_session() is not None

    def run(self, user_task: str, hitl_resolver: object = None) -> dict[str, str]:
        """
        Create root task → plan subtasks → add to scheduler → run executor → return task_id → result.
        hitl_resolver: optional (approval, policy) -> bool for in-process approval prompts.

        When TruLens is enabled the run is recorded via TruCustomApp so inputs,
        outputs, and per-agent calls are stored in the TruLens database.
        """
        if self._trulens_enabled():
            try:
                from devsper import __version__

                _app = _TruSwarmApp(self)
                recorder = make_recorder(_app, app_name="devsper", app_version=__version__)
                if recorder is not None:
                    with recorder as _recording:
                        return _app.execute(user_task, hitl_resolver)
            except Exception as _tru_exc:
                log.warning("TruLens recording setup failed, falling back: %s", _tru_exc)
        return self._run_core(user_task, hitl_resolver)

    def _run_core(self, user_task: str, hitl_resolver: object = None) -> dict[str, str]:
        """Internal run implementation (called directly or via TruLens wrapper)."""
        run_id = getattr(self.event_log, "run_id", "") or ""
        with instrument_swarm_run(run_id, user_task) as span:
            if span is not None:
                span.set_attribute("model_plan", self.planner_model)
                span.set_attribute("model_worker", self.worker_model)
            try:
                self._emit(events.SWARM_STARTED, {"user_task": user_task[:200]})

                root = Task(id="root", description=user_task, dependencies=[])
                from devsper.intelligence.strategy_selector import StrategySelector
                from devsper.intelligence.strategies import get_strategy_for

                knowledge_graph = None
                if self._config is not None:
                    kg_cfg = getattr(self._config, "knowledge", None)
                    if kg_cfg and (getattr(kg_cfg, "guide_planning", False) or getattr(kg_cfg, "auto_extract", False)):
                        from devsper.knowledge.knowledge_graph import KnowledgeGraph
                        from devsper.memory.memory_store import get_default_store
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
                shared_memory_namespace = (
                    f"run:{scheduler.run_id}" if getattr(scheduler, "run_id", "") else None
                )
                _persist_dag(scheduler, self.event_log)

                from devsper.reasoning.store import ReasoningStore
                from devsper.agents.message_bus import SwarmMessageBus

                message_bus = None
                if getattr(self, "message_bus_enabled", True):
                    message_bus = SwarmMessageBus(event_log=self.event_log)

                # Build HITL once for both single-node and executor paths
                hitl_enabled = False
                hitl_escalation_checker = None
                hitl_approval_store = None
                hitl_notifier = None
                if self._config is not None:
                    hitl_cfg = getattr(self._config, "hitl", None)
                    if hitl_cfg and getattr(hitl_cfg, "enabled", False):
                        from devsper.hitl.escalation import EscalationChecker, EscalationPolicy, EscalationTrigger
                        from devsper.hitl.approval import ApprovalStore, ApprovalNotifier
                        policies: list[EscalationPolicy] = []
                        for p in getattr(hitl_cfg, "policies", []) or []:
                            triggers = [
                                EscalationTrigger(type=getattr(t, "type", "confidence_below"), threshold=getattr(t, "threshold", 0.5))
                                for t in getattr(p, "triggers", []) or []
                            ]
                            policies.append(
                                EscalationPolicy(
                                    triggers=triggers,
                                    approvers=getattr(p, "approvers", []) or [],
                                    timeout_seconds=getattr(p, "timeout_seconds", 3600),
                                    on_timeout=getattr(p, "on_timeout", "auto_approve"),
                                )
                            )
                        if policies:
                            hitl_enabled = True
                            hitl_escalation_checker = EscalationChecker(policies)
                            hitl_approval_store = ApprovalStore(getattr(self._config, "data_dir", ".devsper"))
                            hitl_notifier = ApprovalNotifier()

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
                            memory_namespace=shared_memory_namespace,
                            store_result_to_memory=False,
                            use_tools=self.use_tools,
                            reasoning_store=rs,
                            user_task=user_task,
                            parallel_tools=getattr(self, "parallel_tools", True),
                            message_bus=mb,
                        )
                    from devsper.nodes.single import create_single_node
                    single_node = create_single_node(
                        config=self._config or _fake_config(),
                        scheduler=scheduler,
                        event_log=self.event_log,
                        memory_router=self.memory_router,
                        agent_factory=_agent_factory,
                        user_task=user_task,
                        message_bus=message_bus,
                        hitl_enabled=hitl_enabled,
                        hitl_escalation_checker=hitl_escalation_checker,
                        hitl_approval_store=hitl_approval_store,
                        hitl_notifier=hitl_notifier,
                        hitl_resolver=hitl_resolver,
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
                        from devsper.intelligence.analysis.run_report import build_report_from_events
                        from devsper.runtime.run_history import RunHistory
                        log_path = getattr(self.event_log, "log_path", None)
                        if log_path:
                            events_dir = os.path.dirname(log_path)
                            run_id = getattr(self.event_log, "run_id", None)
                            if run_id:
                                report = build_report_from_events(run_id, events_dir)
                                RunHistory().record_run(report)
                                if self._config and getattr(getattr(self._config, "knowledge", None), "auto_extract", False):
                                    from devsper.knowledge.knowledge_graph import KnowledgeGraph
                                    from devsper.knowledge.extractor import KnowledgeExtractor
                                    from devsper.memory.memory_store import get_default_store
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
                    result_obj = RunResult(results)
                    result_obj.budget = {
                        "limit_usd": float(self.budget_usd or 0.0),
                        "spent_usd": 0.0,
                        "remaining_usd": float(self.budget_usd or 0.0),
                        "breakdown": {},
                        "tasks_completed": len(scheduler.get_completed_tasks()),
                        "tasks_skipped": 0,
                    }
                    return result_obj

                reasoning_store = ReasoningStore()
                remote_agents = list(getattr(getattr(self._config, "swarm", None), "remote_agents", []) or [])
                if remote_agents:
                    from devsper.protocol.client import RemoteAgent

                    agent = RemoteAgent(remote_agents, model_name=self.worker_model)
                else:
                    agent = Agent(
                        model_name=self.worker_model,
                        event_log=self.event_log,
                        memory_router=self.memory_router,
                        memory_namespace=shared_memory_namespace,
                        store_result_to_memory=False,
                        use_tools=self.use_tools,
                        reasoning_store=reasoning_store,
                        user_task=user_task,
                        parallel_tools=getattr(self, "parallel_tools", True),
                        message_bus=message_bus,
                    )
                agent_registry = AgentRegistry.from_config(self._config) if self._config is not None else AgentRegistry([])
                audit_logger = None
                if self._config and getattr(getattr(self._config, "compliance", None), "audit_logging", False):
                    run_id = getattr(self.event_log, "run_id", "") or ""
                    if run_id:
                        from devsper.audit.logger import AuditLogger
                        audit_logger = AuditLogger(
                            getattr(self._config, "data_dir", ".devsper"),
                            run_id=run_id,
                        )
                        if hasattr(agent, "audit_logger"):
                            agent.audit_logger = audit_logger
                        if hasattr(agent, "audit_run_id"):
                            agent.audit_run_id = run_id
                task_cache = None
                semantic_cache = None
                if getattr(self, "cache_enabled", False):
                    from devsper.cache import TaskCache

                    task_cache = TaskCache()
                    cfg = getattr(self, "_config", None)
                    if cfg and getattr(getattr(cfg, "cache", None), "semantic", False):
                        from devsper.cache.task_cache import SemanticTaskCache

                        cache_cfg = cfg.cache
                        semantic_cache = SemanticTaskCache(
                            similarity_threshold=getattr(cache_cfg, "similarity_threshold", 0.92),
                            max_age_hours=getattr(cache_cfg, "max_age_hours", 168.0),
                        )
                complexity_router = None
                models_config = None
                if self._config is not None:
                    from devsper.providers.complexity_router import TaskComplexityRouter

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
                        from devsper.agents.critic import CriticAgent
                        critic_agent = CriticAgent(event_log=self.event_log)

                prefetcher = None
                if getattr(self, "speculative_execution", False) and getattr(
                    self, "prefetch_enabled", True
                ):
                    from devsper.swarm.prefetcher import TaskPrefetcher
                    from devsper.tools.selector import get_tools_for_task
                    try:
                        from devsper.tools.scoring import get_default_score_store
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
                        from devsper.bus import get_bus
                        bus = get_bus(self._config)
                    except Exception:
                        pass
                    if getattr(getattr(self._config, "swarm", None), "checkpoint_enabled", True):
                        from devsper.swarm.checkpointer import SchedulerCheckpointer
                        checkpointer = SchedulerCheckpointer(
                            events_dir=getattr(self._config, "events_dir", ".devsper/events"),
                            interval_tasks=getattr(
                                getattr(self._config, "swarm", None), "checkpoint_interval", 10
                            ),
                        )

                from devsper.config import get_config
                sandbox_config = getattr(get_config(), "sandbox", None)
                if remote_agents:
                    sandbox_config = None
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
                    sandbox_config=sandbox_config,
                    audit_logger=audit_logger,
                    hitl_enabled=hitl_enabled,
                    hitl_escalation_checker=hitl_escalation_checker,
                    hitl_approval_store=hitl_approval_store,
                    hitl_notifier=hitl_notifier,
                    hitl_resolver=hitl_resolver,
                    clarification_bus=getattr(self, "clarification_queue", None),
                    budget_manager=BudgetManager(
                        limit_usd=float(self.budget_usd or 0.0),
                        on_exceeded=self.budget_on_exceeded,
                        alert_at_pct=int(getattr(getattr(self._config, "budget", None), "alert_at_pct", 80) if self._config else 80),
                    ),
                    agent_registry=agent_registry,
                )
                self._current_executor = executor
                executor.run_sync()
                _persist_dag(scheduler, self.event_log, getattr(executor, "execution_graph", None))

                self._last_scheduler = scheduler
                self._last_reasoning_store = reasoning_store
                results = scheduler.get_results()
                if self.store_swarm_memory and self.memory_router and results:
                    self._store_swarm_memory(user_task, scheduler)
                self._emit(events.SWARM_FINISHED, {"task_count": len(results)})
                try:
                    from devsper.intelligence.analysis.run_report import build_report_from_events
                    from devsper.runtime.run_history import RunHistory
                    log_path = getattr(self.event_log, "log_path", None)
                    if log_path:
                        events_dir = os.path.dirname(log_path)
                        run_id = getattr(self.event_log, "run_id", None)
                        if run_id:
                            report = build_report_from_events(run_id, events_dir)
                            RunHistory().record_run(report)
                            if self._config and getattr(getattr(self._config, "knowledge", None), "auto_extract", False):
                                from devsper.knowledge.knowledge_graph import KnowledgeGraph
                                from devsper.knowledge.extractor import KnowledgeExtractor
                                from devsper.memory.memory_store import get_default_store
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
                result_obj = RunResult(results)
                if executor.budget_manager is not None:
                    bm = executor.budget_manager
                    total_tasks = len(scheduler.get_all_tasks())
                    done_tasks = len(scheduler.get_completed_tasks())
                    result_obj.budget = {
                        "limit_usd": float(bm.limit_usd),
                        "spent_usd": float(bm.spent_usd),
                        "remaining_usd": float(bm.remaining_usd if bm.limit_usd > 0 else 0.0),
                        "breakdown": bm.breakdown,
                        "tasks_completed": done_tasks,
                        "tasks_skipped": max(0, total_tasks - done_tasks),
                    }
                return result_obj
            except Exception as exc:
                record_exception(span, exc)
                raise

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
        from devsper.swarm.map_reduce import map_reduce as _map_reduce

        workers = worker_count if worker_count is not None else self.worker_count
        return _map_reduce(dataset, map_fn, reduce_fn, worker_count=workers)

    def _store_swarm_memory(self, user_task: str, scheduler: Scheduler) -> None:
        """Store important outputs (research findings, summaries, results) into memory after run."""
        from devsper.memory.memory_store import (
            MemoryStore,
            get_default_store,
            generate_memory_id,
        )
        from devsper.memory.memory_types import MemoryRecord, MemoryType
        from devsper.memory.memory_index import MemoryIndex

        store = getattr(self.memory_router, "store", None)
        if not isinstance(store, MemoryStore):
            store = get_default_store()
        index = getattr(self.memory_router, "index", None) or MemoryIndex(
            store,
            ranking_backend=getattr(self.memory_router, "ranking_backend", "local"),
        )
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
