"""
Worker node: executes tasks, reports heartbeats, claims tasks.
Distributed mode only; requires redis.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from hivemind.types.task import Task
from hivemind.agents.agent import Agent, AgentRequest
from hivemind.bus.message import create_bus_message
from hivemind.bus.topics import (
    TASK_READY,
    TASK_CLAIMED,
    TASK_CLAIM_GRANTED,
    TASK_CLAIM_REJECTED,
    TASK_COMPLETED,
    TASK_FAILED,
    NODE_HEARTBEAT,
    NODE_JOINED,
    SWARM_SNAPSHOT,
    SWARM_CONTROL,
)
from hivemind.cluster.node_info import NodeInfo, NodeRole
from hivemind.cluster.registry import ClusterRegistry
from hivemind.swarm.prefetcher import PrefetchResult

log = logging.getLogger(__name__)


def _require_distributed() -> None:
    try:
        import redis.asyncio  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Distributed mode requires: pip install hivemind-ai[distributed]"
        ) from e


def _node_info_from_config(config: object, node_id: str, role: NodeRole, run_id: str) -> NodeInfo:
    now = datetime.now(timezone.utc).isoformat()
    nodes_cfg = getattr(config, "nodes", None)
    rpc_port = getattr(nodes_cfg, "rpc_port", 7701)
    host = "localhost"
    try:
        import socket
        host = socket.gethostname() or host
    except Exception:
        pass
    rpc_url = f"http://{host}:{rpc_port}"
    tags = list(getattr(nodes_cfg, "node_tags", []) or [])
    max_workers = getattr(nodes_cfg, "max_workers_per_node", 8)
    try:
        import hivemind
        version = getattr(hivemind, "__version__", "1.10.0")
    except Exception:
        version = "1.10.0"
    return NodeInfo(
        node_id=node_id,
        role=role,
        host=host,
        rpc_port=rpc_port,
        rpc_url=rpc_url,
        tags=tags,
        max_workers=max_workers,
        joined_at=now,
        last_heartbeat=now,
        version=version,
    )


def _build_agent_request(
    task: Task,
    memory_router: object,
    tool_selector: object,
    prefetch: PrefetchResult | None,
    user_task: str = "",
    message_bus: object = None,
    score_store: object = None,
) -> AgentRequest:
    """Build AgentRequest for a task (mirrors Agent.run_task context)."""
    memory_section = ""
    if prefetch and getattr(prefetch, "memory_context", None):
        memory_section = prefetch.memory_context or ""
    elif memory_router and task.description:
        try:
            query = f"{user_task} {task.description}".strip() if user_task else task.description
            memory_section = memory_router.get_memory_context(query) or ""
        except Exception:
            pass
    message_bus_section = ""
    if message_bus:
        try:
            message_bus_section = message_bus.get_context_sync(task.id) or ""
        except Exception:
            pass
    if message_bus_section:
        memory_section = (memory_section + "\n\n" + message_bus_section).strip()
    from hivemind.agents.roles import get_role_config
    role_config = get_role_config(getattr(task, "role", None))
    from hivemind.agents.agent import BROADCAST_INSTRUCTION
    broadcast_instruction = BROADCAST_INSTRUCTION if message_bus_section else ""
    system_prompt = role_config.prompt_prefix + broadcast_instruction
    tools_names: list[str] = []
    if tool_selector:
        try:
            if prefetch and getattr(prefetch, "tools", None):
                tools_names = [t.name for t in prefetch.tools]
            else:
                tools = tool_selector(
                    task.description or "",
                    role=getattr(task, "role", None),
                    score_store=score_store,
                )
                tools_names = [t.name for t in tools] if tools else []
        except Exception:
            pass
    return AgentRequest(
        task=task,
        memory_context=memory_section,
        tools=tools_names,
        model="mock",
        system_prompt=system_prompt,
        prefetch_used=prefetch is not None,
    )


class WorkerNode:
    """Executes tasks, owns local memory/tool cache, reports results."""

    def __init__(
        self,
        config: object,
        bus: object,
        registry: ClusterRegistry,
        memory_router: object,
        tool_selector: object,
        score_store: object,
        prefetcher: object,
        agent_factory: object,
        event_log: object,
        run_id: str,
        user_task: str = "",
        message_bus: object = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.registry = registry
        self.memory_router = memory_router
        self.tool_selector = tool_selector
        self.score_store = score_store
        self.prefetcher = prefetcher
        self.agent_factory = agent_factory
        self.event_log = event_log
        self._run_id = run_id
        self.user_task = user_task or ""
        self.message_bus = message_bus
        self.node_id = _make_node_id()
        nodes_cfg = getattr(config, "nodes", None)
        role = NodeRole.WORKER
        self.node_info = _node_info_from_config(config, self.node_id, role, run_id)
        self._active_tasks = 0
        self._pending_grants: dict[str, asyncio.Event] = {}
        self._current_tasks: dict[str, Task] = {}
        self._task_durations: list[float] = []
        self._last_completed_ids: list[str] = []
        self._paused = False
        self._draining = False
        self._snapshot: dict | None = None

    async def start(self) -> None:
        await self.registry.register(self.node_info)
        await self.bus.subscribe(TASK_READY, self._on_task_ready)
        await self.bus.subscribe(TASK_CLAIM_GRANTED, self._on_claim_granted)
        await self.bus.subscribe(TASK_CLAIM_REJECTED, self._on_claim_rejected)
        await self.bus.subscribe(SWARM_SNAPSHOT, self._on_snapshot)
        await self.bus.subscribe(SWARM_CONTROL, self._on_control)
        asyncio.create_task(self.heartbeat_loop())
        await self.bus.publish(
            create_bus_message(
                topic=NODE_JOINED,
                payload=self.node_info.to_dict(),
                sender_id=self.node_id,
                run_id=self._run_id,
            )
        )

    async def _on_task_ready(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        target = payload.get("target_worker_id")
        if target is not None and target != self.node_id:
            return
        if self._paused or self._draining:
            return
        if self._active_tasks >= self.node_info.max_workers:
            return
        try:
            task = Task.from_dict(payload)
        except Exception:
            return
        self._pending_grants[task.id] = asyncio.Event()
        await self.bus.publish(
            create_bus_message(
                topic=TASK_CLAIMED,
                payload={"task_id": task.id, "worker_id": self.node_id},
                sender_id=self.node_id,
                run_id=self._run_id,
            )
        )
        try:
            await asyncio.wait_for(self._pending_grants[task.id].wait(), timeout=2.0)
        except asyncio.TimeoutError:
            self._pending_grants.pop(task.id, None)
            return
        if task.id not in self._pending_grants:
            return
        self._pending_grants.pop(task.id, None)
        self._active_tasks += 1
        asyncio.create_task(self._execute_task(task))

    async def _on_claim_granted(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        if payload.get("worker_id") != self.node_id:
            return
        task_id = payload.get("task_id")
        if task_id and task_id in self._pending_grants:
            self._pending_grants[task_id].set()

    async def _on_claim_rejected(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        if payload.get("worker_id") != self.node_id:
            return
        task_id = payload.get("task_id")
        if task_id:
            self._pending_grants.pop(task_id, None)

    async def _execute_task(self, task: Task) -> None:
        self._current_tasks[task.id] = task
        start = time.monotonic()
        try:
            prefetch = self.prefetcher.consume(task.id) if self.prefetcher else None
            request = _build_agent_request(
                task,
                self.memory_router,
                self.tool_selector,
                prefetch,
                user_task=self.user_task,
                message_bus=self.message_bus,
                score_store=self.score_store,
            )
            agent = self.agent_factory(self.config)
            if hasattr(agent, "model_name") and hasattr(self.config, "models"):
                request = AgentRequest(
                    task=request.task,
                    memory_context=request.memory_context,
                    tools=request.tools,
                    model=getattr(self.config.models, "worker", "mock"),
                    system_prompt=request.system_prompt,
                    prefetch_used=request.prefetch_used,
                )
            response = await asyncio.to_thread(agent.run, request)
            self._task_durations.append(time.monotonic() - start)
            if len(self._task_durations) > 10:
                self._task_durations.pop(0)
            self._last_completed_ids.append(task.id)
            if len(self._last_completed_ids) > 50:
                self._last_completed_ids.pop(0)
            await self.bus.publish(
                create_bus_message(
                    topic=TASK_COMPLETED,
                    payload=response.to_dict(),
                    sender_id=self.node_id,
                    run_id=self._run_id,
                )
            )
        except Exception as e:
            await self.bus.publish(
                create_bus_message(
                    topic=TASK_FAILED,
                    payload={
                        "task_id": task.id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "worker_id": self.node_id,
                    },
                    sender_id=self.node_id,
                    run_id=self._run_id,
                )
            )
        finally:
            self._active_tasks -= 1
            self._current_tasks.pop(task.id, None)

    async def heartbeat_loop(self) -> None:
        interval = 10.0
        nodes_cfg = getattr(self.config, "nodes", None)
        if nodes_cfg:
            interval = getattr(nodes_cfg, "heartbeat_interval_seconds", 10.0)
        while True:
            await asyncio.sleep(interval)
            if self._paused:
                continue
            avg_duration = (
                sum(self._task_durations) / len(self._task_durations)
                if self._task_durations else 0.0
            )
            cached_tools: list[str] = []
            if self.score_store and hasattr(self.score_store, "get_cached_tool_names"):
                try:
                    cached_tools = list(self.score_store.get_cached_tool_names())
                except Exception:
                    pass
            await self.bus.publish(
                create_bus_message(
                    topic=NODE_HEARTBEAT,
                    payload={
                        "node_id": self.node_id,
                        "active_tasks": self._active_tasks,
                        "max_workers": self.node_info.max_workers,
                        "avg_task_duration_seconds": avg_duration,
                        "load": self._active_tasks / max(1, self.node_info.max_workers),
                        "cached_tools": cached_tools,
                        "completed_task_ids": self._last_completed_ids[-50:],
                        "tags": self.node_info.tags,
                        "rpc_url": self.node_info.rpc_url,
                    },
                    sender_id=self.node_id,
                    run_id=self._run_id,
                )
            )
            try:
                await self.registry.heartbeat(
                    self.node_id,
                    {"last_heartbeat": datetime.now(timezone.utc).isoformat()},
                )
            except Exception:
                pass

    async def _on_control(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        command = payload.get("command")
        target = payload.get("target", "all")
        if target != "all" and target != self.node_id:
            return
        if command == "pause":
            self._paused = True
        elif command == "resume":
            self._paused = False
        elif command == "drain":
            self._draining = True

    async def _on_snapshot(self, msg: object) -> None:
        self._snapshot = getattr(msg, "payload", None)

    def get_current_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self._current_tasks.values()]


def _make_node_id() -> str:
    from uuid import uuid4
    return str(uuid4())
