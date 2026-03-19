"""
Controller node: dispatch logic, cluster state, leader election.
Distributed mode only; requires redis, fastapi, uvicorn.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
import os
import sys

from devsper.bus.message import create_bus_message
from devsper.bus.topics import (
    TASK_READY,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_CLAIMED,
    TASK_CLAIM_GRANTED,
    TASK_CLAIM_REJECTED,
    TASK_TOOL_CALLS,
    TOOL_RESULTS,
    NODE_HEARTBEAT,
    NODE_JOINED,
    NODE_LEFT,
    NODE_BECAME_LEADER,
    NODE_LOST_LEADERSHIP,
    SWARM_SNAPSHOT,
    SWARM_STATUS_REQUEST,
    SWARM_STATUS_RESPONSE,
)
from devsper.types.event import Event, events as event_types
from devsper.agents.agent import AgentResponse
from devsper.cluster.node_info import NodeInfo, NodeRole
from devsper.cluster.registry import ClusterRegistry
from devsper.cluster.election import LeaderElector
from devsper.cluster.state_backend import StateBackend
from devsper.cluster.router import TaskRouter
from devsper.swarm.scheduler import Scheduler
from devsper.runtime.clarification_manager import ClarificationManager
from devsper.types.task import TaskStatus as TaskStatusEnum
from devsper.runtime.task_state import TaskStateMachine
from devsper.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


def _require_distributed() -> None:
    try:
        import redis.asyncio  # noqa: F401
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Distributed mode requires: pip install devsper[distributed]"
        ) from e


def _node_info_from_config(config: object, node_id: str, role: NodeRole, run_id: str) -> NodeInfo:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    nodes_cfg = getattr(config, "nodes", None)
    rpc_port = getattr(nodes_cfg, "rpc_port", 7700)
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
        import devsper
        version = getattr(devsper, "__version__", "1.10.0")
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


class ControllerNode:
    """Owns dispatch, cluster state, leader election. No agent execution."""

    def __init__(
        self,
        config: object,
        scheduler: Scheduler,
        bus: object,
        state_backend: StateBackend,
        registry: ClusterRegistry,
        elector: LeaderElector,
        router: TaskRouter,
        event_log: object,
    ) -> None:
        self.config = config
        self.scheduler = scheduler
        self.bus = bus
        self.state_backend = state_backend
        self.registry = registry
        self.elector = elector
        self.router = router
        self.event_log = event_log
        self.run_id = getattr(scheduler, "run_id", "") or ""
        nodes_cfg = getattr(config, "nodes", None)
        role_str = getattr(nodes_cfg, "role", "controller")
        role = NodeRole.CONTROLLER if role_str == "controller" else NodeRole.HYBRID
        self.node_id = _make_node_id()
        self.node_info = _node_info_from_config(config, self.node_id, role, self.run_id)
        self._is_leader = False
        self._pending_claims: dict[str, dict] = {}
        self._worker_stats: dict[str, dict] = {}
        self._leader_tasks: list[asyncio.Task] = []
        self._started_at = time.monotonic()
        self._last_no_workers_log: float = 0.0
        self._clarification_manager: ClarificationManager | None = None
        self._clarification_bridge_task: asyncio.Task | None = None
        self._run_view: object | None = None
        self._state: TaskStateMachine | None = None
        self._dispatch_wakeup = asyncio.Event()

    async def start(self) -> None:
        await self.registry.register(self.node_info)
        await self.bus.subscribe(TASK_COMPLETED, self._on_task_completed, run_id=self.run_id)
        await self.bus.subscribe(TASK_FAILED, self._on_task_failed, run_id=self.run_id)
        await self.bus.subscribe(TASK_CLAIMED, self._on_task_claimed, run_id=self.run_id)
        await self.bus.subscribe(TASK_TOOL_CALLS, self._on_task_tool_calls, run_id=self.run_id)
        await self.bus.subscribe(NODE_HEARTBEAT, self._on_heartbeat, run_id=self.run_id)
        await self.bus.subscribe(NODE_JOINED, self._on_node_joined, run_id=self.run_id)
        await self.bus.subscribe(NODE_LEFT, self._on_node_left, run_id=self.run_id)
        await self.bus.subscribe(SWARM_STATUS_REQUEST, self._on_status_request, run_id=self.run_id)
        asyncio.create_task(self._registry_heartbeat_loop())
        # Clarification manager + bus bridge (controller owns serialization)
        self._clarification_manager = ClarificationManager()
        # Authoritative task state machine for this run
        try:
            self._state = TaskStateMachine(self.scheduler.get_all_tasks())
        except Exception:
            self._state = None

        # Task-level injection: append user clarification context for re-dispatch.
        # Also mirror into scheduler description so snapshots include it.
        def _append_ctx(task_id: str, text: str) -> None:
            if self._state is not None:
                self._state.append_context(task_id, text)
            try:
                self.scheduler.append_task_context(task_id, text)
            except Exception:
                pass

        self._clarification_manager.on_task_context_update = _append_ctx
        asyncio.create_task(self._clarification_manager.run_dispatch_loop())
        self._clarification_bridge_task = asyncio.create_task(self._bridge_clarification_requests())

        # Optional: controller-side rich Live view.
        # Disabled when headless (DEVSPER_HEADLESS=1), CI, or DEVSPER_CONTROLLER_TUI=0.
        # When no TUI, on_clarification_ready is never set so ClarificationManager uses defaults.
        _headless = os.environ.get("DEVSPER_HEADLESS", "0").strip().lower() in ("1", "true", "yes")
        if (
            not _headless
            and sys.stdout.isatty()
            and not os.environ.get("CI")
            and os.environ.get("DEVSPER_CONTROLLER_TUI", "1").strip() != "0"
        ):
            try:
                log_path = getattr(getattr(self, "event_log", None), "log_path", None)
                from devsper.cli.ui.run_view import DistributedRunView

                mgr = self.get_clarification_manager()
                view = DistributedRunView(
                    log_path=log_path,
                    run_id=self.run_id,
                    stop_check=lambda: self.scheduler.is_finished(),
                    poll_interval=0.1,
                    clarification_manager=mgr,
                )
                self._run_view = view
                await view.start()
                asyncio.create_task(self._stop_run_view_when_finished())
            except Exception:
                log.warning("Controller TUI failed to start; HITL prompts will auto-resolve with defaults", exc_info=False)
        asyncio.create_task(
            self.elector.watch(
                self.node_id,
                self._become_leader,
                self._lose_leadership,
            )
        )

    def get_clarification_manager(self) -> ClarificationManager | None:
        return self._clarification_manager

    async def _bridge_clarification_requests(self) -> None:
        """
        Bridge: bus -> manager (submit) -> bus (response).
        Runs on controller. Safe for multi-node: manager serializes prompts.
        """
        if self._clarification_manager is None:
            return
        async for request, node_id in self.bus.subscribe_clarification_requests(self.run_id):
            asyncio.create_task(
                self._handle_one_clarification(request=request, node_id=node_id)
            )

    async def _handle_one_clarification(self, *, request: object, node_id: str) -> None:
        if self._clarification_manager is None:
            return
        # Transition task to WAITING while prompt is active.
        try:
            task_id = getattr(request, "task_id", "") or ""
            if task_id and self._state is not None:
                self._state.mark_waiting(task_id)
            if task_id:
                try:
                    self.scheduler.set_task_status(task_id, TaskStatusEnum.WAITING_FOR_INPUT)
                except Exception:
                    pass
            if task_id and self._run_view is not None:
                getattr(self._run_view, "on_task_status_changed")(task_id, "waiting_for_input", node_id)
        except Exception:
            pass
        try:
            response = await self._clarification_manager.submit(request, node_id=node_id)
        except Exception:
            from devsper.events import ClarificationResponse

            response = ClarificationResponse(request_id=getattr(request, "request_id", ""), answers={}, skipped=True)
        try:
            await self.bus.publish_clarification_response(self.run_id, response)
        except Exception:
            pass
        # Wake dispatcher (new context may make task runnable again).
        try:
            task_id = getattr(request, "task_id", "") or ""
            if task_id and self._state is not None:
                self._state.mark_running(task_id, worker_id=node_id)
            if task_id and self._run_view is not None:
                getattr(self._run_view, "on_task_status_changed")(task_id, "running", node_id)
        except Exception:
            pass
        self._dispatch_wakeup.set()

    async def _registry_heartbeat_loop(self) -> None:
        interval = 10.0
        nodes_cfg = getattr(self.config, "nodes", None)
        if nodes_cfg:
            interval = getattr(nodes_cfg, "heartbeat_interval_seconds", 10.0)
        while True:
            try:
                await asyncio.sleep(interval)
                now = datetime.now(timezone.utc).isoformat()
                await self.registry.heartbeat(self.node_id, {"last_heartbeat": now})
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _become_leader(self) -> None:
        self._is_leader = True
        # Ensure tool modules are imported so ToolRegistry/from_global isn't empty.
        # devsper.tools imports categories and registers built-in tools via side effects.
        try:
            import devsper.tools  # noqa: F401
        except Exception:
            pass
        current_ids = {t.id for t in self.scheduler.get_all_tasks()}
        current_done = sum(
            1
            for t in self.scheduler.get_all_tasks()
            if getattr(t, "status", None) in (TaskStatusEnum.COMPLETED, TaskStatusEnum.FAILED)
        )
        snapshot = await self.state_backend.load_snapshot(self.run_id)
        if snapshot:
            snapshot_ids = {
                t.get("id") for t in snapshot.get("tasks", []) if t.get("id")
            }
            if snapshot_ids == current_ids:
                # Avoid rollback on leadership flaps: restore only if snapshot is strictly ahead.
                snapshot_done = 0
                try:
                    for t in snapshot.get("tasks", []):
                        st = t.get("status")
                        # TaskStatus enum values are ints in serialized snapshot (2=COMPLETED, 3=FAILED).
                        if st in (2, 3):
                            snapshot_done += 1
                except Exception:
                    snapshot_done = int(snapshot.get("completed_count", 0) or 0)
                if snapshot_done > current_done:
                    self.scheduler = Scheduler.restore(snapshot)
                    log.info(
                        "Restored scheduler from snapshot: %s tasks already done",
                        snapshot.get("completed_count", 0),
                    )
                else:
                    log.debug(
                        "Skip snapshot restore (snapshot_done=%s <= current_done=%s)",
                        snapshot_done,
                        current_done,
                    )
                # Rebuild and hydrate state machine so dispatch loop sees correct readiness.
                try:
                    self._state = TaskStateMachine(self.scheduler.get_all_tasks())
                    for t in self.scheduler.get_all_tasks():
                        tid = getattr(t, "id", None)
                        if not tid:
                            continue
                        st = getattr(t, "status", None)
                        if st == TaskStatusEnum.COMPLETED:
                            self._state.mark_complete(tid, (getattr(t, "result", None) or "") or "")
                        elif st == TaskStatusEnum.FAILED:
                            self._state.mark_failed(tid, (getattr(t, "error", None) or "") or "")
                except Exception:
                    log.warning("Failed to rebuild state machine after restore", exc_info=True)
            else:
                # Stale snapshot from a different run (e.g. new prompt); discard it
                await self.state_backend.delete_snapshot(self.run_id)
        self._leader_tasks = [
            asyncio.create_task(self.dispatch_loop()),
            asyncio.create_task(self.checkpoint_loop()),
            asyncio.create_task(self.heartbeat_monitor()),
            asyncio.create_task(self.worker_timeout_monitor()),
        ]
        # Broadcast run.start with tool registry. Include redis_url only when bus backend is Redis
        # (single-node must not require Redis).
        try:
            nodes_cfg = getattr(self.config, "nodes", None)
            bus_cfg = getattr(self.config, "bus", None)
            payload = {
                "run_id": self.run_id,
                "tool_registry": ToolRegistry.from_global().to_dict(),
            }
            try:
                backend = getattr(bus_cfg, "backend", None) or ""
                if str(backend).strip().lower() == "redis":
                    payload["redis_url"] = (
                        getattr(bus_cfg, "redis_url", None)
                        or os.environ.get("DEVSPER_REDIS_URL")
                        or "redis://localhost:6379"
                    )
            except Exception:
                pass
            await self.bus.publish(
                create_bus_message(
                    topic=f"run.start.{self.run_id}",
                    payload=payload,
                    sender_id=self.node_id,
                    run_id=self.run_id,
                )
            )
        except Exception:
            pass
        await self.bus.publish(
            create_bus_message(
                topic=NODE_BECAME_LEADER,
                payload={"node_id": self.node_id, "run_id": self.run_id},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )

    async def _lose_leadership(self) -> None:
        self._is_leader = False
        for t in self._leader_tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._leader_tasks.clear()
        try:
            if self._run_view is not None:
                await getattr(self._run_view, "stop")()
        except Exception:
            pass
        await self.bus.publish(
            create_bus_message(
                topic=NODE_LOST_LEADERSHIP,
                payload={"node_id": self.node_id},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )

    async def _stop_run_view_when_finished(self) -> None:
        while True:
            try:
                if self.scheduler.is_finished():
                    break
            except Exception:
                break
            await asyncio.sleep(0.1)
        try:
            if self._run_view is not None:
                await getattr(self._run_view, "stop")()
        except Exception:
            pass

    async def dispatch_loop(self) -> None:
        timeout_sec = 120
        # If a worker never claims (e.g. dropped TASK_READY due to no free slot), requeue soon so we re-dispatch.
        claim_wait_sec = 30
        nodes_cfg = getattr(self.config, "nodes", None)
        if nodes_cfg:
            timeout_sec = getattr(nodes_cfg, "task_claim_timeout_seconds", 120)
            claim_wait_sec = getattr(nodes_cfg, "task_claim_wait_seconds", 30)
        _waited_for_workers = False
        while not self.scheduler.is_finished():
            if not self._is_leader:
                break
            # Compute readiness via state machine (authoritative), fall back to scheduler if absent.
            if self._state is not None:
                ready_ids = self._state.get_ready_tasks()
                ready = []
                for tid in ready_ids:
                    try:
                        ready.append(self.scheduler.get_task(tid))
                    except Exception:
                        continue
            else:
                ready = self.scheduler.get_ready_tasks()
            workers = await self.registry.get_workers()
            if self._worker_stats:
                workers = [w for w in workers if w.node_id in self._worker_stats]
            # Drop stale registry entries that won't claim tasks.
            try:
                now = datetime.now(timezone.utc)
                fresh: list = []
                for w in workers:
                    hb = getattr(w, "last_heartbeat", "") or ""
                    try:
                        dt = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
                        if (now - dt).total_seconds() <= 30:
                            fresh.append(w)
                    except Exception:
                        fresh.append(w)
                workers = fresh
            except Exception:
                pass
            # Give workers time to register before first dispatch so we spread across all (avoid 429)
            if ready and not _waited_for_workers:
                if len(workers) < 2:
                    for _ in range(10):
                        await asyncio.sleep(0.25)
                        workers = await self.registry.get_workers()
                        if len(workers) >= 2:
                            break
                _waited_for_workers = True
            now_ts = time.monotonic()
            # Only dispatch to workers that have a free slot (avoid sending TASK_READY to workers at capacity).
            def _workers_with_capacity() -> list:
                out = []
                for w in workers:
                    count = sum(
                        1
                        for _pid, p in self._pending_claims.items()
                        if (p.get("target_worker") == w.node_id or p.get("worker_id") == w.node_id)
                    )
                    max_slots = getattr(w, "max_workers", 1) or 1
                    if count < max_slots:
                        out.append(w)
                return out

            for task in ready:
                if task.id in self._pending_claims:
                    pending = self._pending_claims[task.id]
                    elapsed = now_ts - pending.get("dispatched_at", 0)
                    if pending.get("claimed"):
                        if elapsed > timeout_sec:
                            del self._pending_claims[task.id]
                            log.warning("Task %s claim timed out, re-queuing", task.id)
                            if self._state is not None:
                                self._state.requeue(task.id)
                    else:
                        # Never claimed (worker dropped TASK_READY e.g. no slot); requeue soon to re-dispatch
                        if elapsed > claim_wait_sec:
                            del self._pending_claims[task.id]
                            log.warning(
                                "Task %s unclaimed after %.0fs, re-queuing",
                                task.id[:8],
                                elapsed,
                            )
                            if self._state is not None:
                                self._state.requeue(task.id)
                    continue
                if self._state is not None:
                    st = self._state.status_of(task.id)
                    if st is not None and str(st) not in ("TaskRunStatus.READY", "READY"):
                        # Safety: do not dispatch tasks not READY in authoritative state.
                        continue
                workers_eligible = _workers_with_capacity()
                worker = self.router.route(task, workers_eligible, self._worker_stats) if workers_eligible else None
                if worker is None:
                    if not workers and (now_ts - self._last_no_workers_log) >= 10.0:
                        log.warning("No workers in registry; start workers first (run_worker.py).")
                        self._last_no_workers_log = now_ts
                    continue
                # Add before publish so _on_task_claimed sees the entry when worker replies immediately
                self._pending_claims[task.id] = {
                    "dispatched_at": now_ts,
                    "target_worker": worker.node_id,
                    "claimed": False,
                }
                if self._state is not None:
                    self._state.mark_dispatched(task.id, worker_id=worker.node_id)
                deps = getattr(task, "depends_on", None) or getattr(task, "dependencies", None) or []
                log.info(
                    "dispatching task %s with %s dependencies satisfied",
                    task.id[:8],
                    len(deps or []),
                )
                try:
                    if self._run_view is not None:
                        getattr(self._run_view, "on_task_status_changed")(task.id, "pending", worker.node_id)
                except Exception:
                    pass
                # Prefer using tools to proceed; only ask the user an MCQ when you truly need one
                # choice that tools cannot provide. Use search/files/arxiv etc. first.
                base = (task.description or "").strip()
                mcq_hint = (
                    "\n\n[Use available tools (search, read_file, arxiv, etc.) to gather information and proceed. "
                    "Only ask the user a multiple-choice question if you genuinely need a single preference "
                    "that tools cannot infer. If you must ask, use EXACTLY this format:\n"
                    "1) Question text\n- A: option A\n- B: option B\n- C: option C\n"
                    "Return ONLY that MCQ block (no other text).]\n"
                )
                payload = {**task.to_dict(), "target_worker_id": worker.node_id}
                # Description enrichment (Phase 2.3): compute at dispatch time from immutable original + dep outputs.
                if self._state is not None:
                    d = self._state.build_dispatchable(task.id)
                    before_len = len(base)
                    enriched = d.enriched_description
                    after_len = len(enriched)
                    payload["description"] = (enriched + mcq_hint).strip()
                    log.info(
                        "task %s description_len before=%s after=%s",
                        task.id[:8],
                        before_len,
                        after_len,
                    )
                else:
                    payload["description"] = (base + mcq_hint).strip()
                try:
                    reg = ToolRegistry.from_global()
                    payload["tools"] = [t.name for t in reg.list()][:30]
                except Exception:
                    payload["tools"] = []
                await self.bus.publish(
                    create_bus_message(
                        topic=TASK_READY,
                        payload=payload,
                        sender_id=self.node_id,
                        run_id=self.run_id,
                    )
                )
            # Sleep or wait for wakeup (events / clarification).
            self._dispatch_wakeup.clear()
            try:
                await asyncio.wait_for(self._dispatch_wakeup.wait(), timeout=0.05)
            except asyncio.TimeoutError:
                pass

    async def checkpoint_loop(self) -> None:
        while self._is_leader:
            await asyncio.sleep(30)
            try:
                snapshot = self.scheduler.snapshot()
                await self.state_backend.save_snapshot(self.run_id, snapshot)
            except Exception:
                pass

    async def _on_task_claimed(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        task_id = payload.get("task_id")
        worker_id = payload.get("worker_id")
        if not task_id or not worker_id:
            return
        pending = self._pending_claims.get(task_id)
        if not pending or pending.get("claimed"):
            await self.bus.publish(
                create_bus_message(
                    topic=TASK_CLAIM_REJECTED,
                    payload={"task_id": task_id, "worker_id": worker_id},
                    sender_id=self.node_id,
                    run_id=self.run_id,
                )
            )
            return
        pending["claimed"] = True
        pending["worker_id"] = worker_id
        if self._state is not None:
            self._state.mark_running(task_id, worker_id=worker_id)
        log.info("Worker %s claimed task %s", worker_id[:8], task_id[:8])
        self._append_event(event_types.TASK_STARTED, {"task_id": task_id})
        try:
            if self._run_view is not None:
                getattr(self._run_view, "on_task_status_changed")(task_id, "running", worker_id)
        except Exception:
            pass
        await self.bus.publish(
            create_bus_message(
                topic=TASK_CLAIM_GRANTED,
                payload={"task_id": task_id, "worker_id": worker_id},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )
        self._dispatch_wakeup.set()

    def _append_event(self, event_type: event_types, payload: dict) -> None:
        """Write an event to the event log so the TUI (RunViewState.update_from_events) can show progress."""
        el = getattr(self, "event_log", None)
        if el is None or not hasattr(el, "append_event"):
            return
        try:
            el.append_event(
                Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
            )
        except Exception as e:
            log.debug("event_log.append_event failed: %s", e)

    async def _on_task_tool_calls(self, msg: object) -> None:
        """Worker sent tool_calls; run tools and publish TOOL_RESULTS."""
        payload = getattr(msg, "payload", {}) or {}
        task_id = (payload.get("task_id") or "").strip()
        worker_id = getattr(msg, "sender_id", "") or (payload.get("worker_id") or "").strip()
        tool_calls = payload.get("tool_calls")
        if not task_id or not worker_id or not isinstance(tool_calls, list) or len(tool_calls) == 0:
            return
        await self._run_tool_calls_and_send_results(task_id, worker_id, tool_calls)

    async def _run_tool_calls_and_send_results(
        self, task_id: str, worker_id: str, tool_calls: list,
    ) -> None:
        """Execute tools (controller has registry from run.start) and publish TOOL_RESULTS."""
        from devsper.tools.tool_runner import run_tool
        import json
        results: list[dict] = []
        for call in tool_calls:
            name = (call.get("name") or call.get("tool_name") or "").strip()
            args_raw = call.get("arguments") or call.get("args") or {}
            if isinstance(args_raw, str):
                try:
                    args_raw = json.loads(args_raw) if args_raw.strip() else {}
                except Exception:
                    args_raw = {}
            if not isinstance(args_raw, dict):
                args_raw = {}
            result = run_tool(name, args_raw, task_type=None)
            results.append({"name": name, "result": result or ""})
            # Emit to event log so TUI "Tools" panel shows activity.
            self._append_event(
                event_types.TOOL_CALLED,
                {
                    "task_id": task_id,
                    "tool": name,
                    "result_preview": (result or "")[:200],
                },
            )
        await self.bus.publish(
            create_bus_message(
                topic=TOOL_RESULTS,
                payload={"task_id": task_id, "tool_results": results},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )
        tool_names = ", ".join((r.get("name") or "?") for r in results[:4])
        if len(results) > 4:
            tool_names += ", ..."
        log.info(
            "Sent TOOL_RESULTS for task %s (%s tools: %s) to worker %s",
            task_id[:8],
            len(results),
            tool_names,
            worker_id[:8],
        )

    async def _on_task_completed(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        sender_id = getattr(msg, "sender_id", "")
        try:
            tid = (payload.get("task_id") or payload.get("task", {}).get("id") or "").strip() if isinstance(payload, dict) else ""
            if tid:
                log.info("Controller received TASK_COMPLETED task_id=%s from=%s", tid[:8], (sender_id or "")[:8])
        except Exception:
            pass
        # Optional tool-calling protocol: worker may send tool_calls instead of final result.
        tool_calls = payload.get("tool_calls") if isinstance(payload, dict) else None
        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            await self._run_tool_calls_and_send_results(
                task_id=payload.get("task_id") or "",
                worker_id=sender_id,
                tool_calls=tool_calls,
            )
            return
        task_id_raw = ""
        result_text_raw = ""
        duration_s_raw = 0.0
        error_raw = None
        if isinstance(payload, dict):
            task_id_raw = str(payload.get("task_id") or "").strip()
            result_text_raw = str(payload.get("result") or "").strip()
            try:
                duration_s_raw = float(payload.get("duration_seconds") or 0.0)
            except Exception:
                duration_s_raw = 0.0
            error_raw = payload.get("error")

        try:
            response = AgentResponse.from_dict(payload)
            task_id = (response.task_id or "").strip() or task_id_raw
            result_text = (response.result or "").strip()
            if not result_text and result_text_raw:
                result_text = result_text_raw
            duration_s = float(response.duration_seconds or 0.0)
            if duration_s <= 0 and duration_s_raw > 0:
                duration_s = duration_s_raw
            err = response.error or error_raw
        except Exception as e:
            # Rust/Python workers may evolve payload shape; do not stall the run if task_id exists.
            if not task_id_raw:
                log.warning(
                    "TASK_COMPLETED parse failed (no task_id): %s (payload keys: %s)",
                    e,
                    list(payload.keys()) if isinstance(payload, dict) else type(payload),
                )
                return
            log.warning(
                "TASK_COMPLETED parse failed, using raw payload for task_id=%s: %s",
                task_id_raw[:8],
                e,
            )
            task_id = task_id_raw
            result_text = result_text_raw
            duration_s = duration_s_raw
            err = error_raw

        if not result_text and err:
            result_text = f"(Error: {err})"
            log.warning(
                "TASK_COMPLETED empty result for task_id=%s from %s: %s",
                task_id[:12] if task_id else "",
                sender_id[:8] if sender_id else "",
                str(err)[:80] if err else "",
            )
        elif not result_text:
            log.warning(
                "TASK_COMPLETED empty result for task_id=%s from %s (set DEVSPER_WORKER_MODEL on Rust workers to match controller worker model, e.g. github:gpt-4o)",
                task_id[:12] if task_id else "",
                sender_id[:8] if sender_id else "",
            )

        if self._state is not None and task_id:
            self._state.mark_complete(task_id, result_text or "")
        self.scheduler.mark_completed(task_id, result_text or "")
        self._pending_claims.pop(task_id, None)
        duration_ms = int((duration_s or 0) * 1000)
        self._append_event(
            event_types.TASK_COMPLETED,
            {"task_id": task_id, "duration_ms": duration_ms},
        )
        if self.scheduler.is_finished():
            self._append_event(event_types.EXECUTOR_FINISHED, {})
        try:
            if self._run_view is not None:
                getattr(self._run_view, "on_task_status_changed")(task_id, "completed", sender_id)
        except Exception:
            pass
        if sender_id and sender_id not in self._worker_stats:
            self._worker_stats[sender_id] = {}
        if sender_id:
            self._worker_stats[sender_id].setdefault("completed_task_ids", [])
            self._worker_stats[sender_id]["completed_task_ids"] = (
                self._worker_stats[sender_id]["completed_task_ids"][-49:]
                + [task_id]
            )
        self._dispatch_wakeup.set()
        try:
            snapshot = self.scheduler.snapshot()
            await self.state_backend.save_snapshot(self.run_id, snapshot)
        except Exception:
            pass

    async def _on_task_failed(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        task_id = payload.get("task_id")
        error = payload.get("error", "")
        if task_id:
            if self._state is not None:
                self._state.mark_failed(task_id, error)
            self.scheduler.mark_failed(task_id, error)
            self._pending_claims.pop(task_id, None)
            self._append_event(event_types.TASK_FAILED, {"task_id": task_id, "error": error})
            if self.scheduler.is_finished():
                self._append_event(event_types.EXECUTOR_FINISHED, {})
            try:
                if self._run_view is not None:
                    getattr(self._run_view, "on_task_status_changed")(task_id, "failed", "")
            except Exception:
                pass

    async def _on_heartbeat(self, msg: object) -> None:
        sender_id = getattr(msg, "sender_id", "")
        payload = getattr(msg, "payload", {}) or {}
        if not sender_id:
            return
        first_seen = sender_id not in self._worker_stats
        self._worker_stats[sender_id] = dict(payload)
        self._worker_stats[sender_id]["last_seen"] = datetime.now(timezone.utc)
        if first_seen:
            try:
                if self._run_view is not None:
                    getattr(self._run_view, "on_worker_connected")(sender_id)
            except Exception:
                pass
        try:
            await self.registry.heartbeat(
                sender_id, {"last_heartbeat": datetime.now(timezone.utc).isoformat()}
            )
        except Exception:
            pass
        self._dispatch_wakeup.set()

    async def _on_node_joined(self, msg: object) -> None:
        if not self._is_leader:
            return
        try:
            payload = getattr(msg, "payload", {}) or {}
            node_id = payload.get("node_id") or getattr(msg, "sender_id", "")
            if node_id and self._run_view is not None:
                getattr(self._run_view, "on_worker_connected")(node_id)
        except Exception:
            pass
        try:
            snapshot = self.scheduler.snapshot()
            await self.bus.publish(
                create_bus_message(
                    topic=SWARM_SNAPSHOT,
                    payload=snapshot,
                    sender_id=self.node_id,
                    run_id=self.run_id,
                )
            )
        except Exception:
            pass

    async def _on_node_left(self, msg: object) -> None:
        try:
            payload = getattr(msg, "payload", {}) or {}
            node_id = payload.get("node_id") or getattr(msg, "sender_id", "")
            if node_id and self._run_view is not None:
                getattr(self._run_view, "on_worker_disconnected")(node_id)
        except Exception:
            pass

    async def worker_timeout_monitor(self) -> None:
        while self._is_leader:
            await asyncio.sleep(10)
            now_ts = datetime.now(timezone.utc)
            for worker_id, stats in list(self._worker_stats.items()):
                last_seen = stats.get("last_seen")
                if not last_seen:
                    continue
                try:
                    delta = (now_ts - last_seen).total_seconds()
                except Exception:
                    try:
                        from datetime import datetime as dt_cls
                        dt = dt_cls.fromisoformat(str(last_seen).replace("Z", "+00:00"))
                        delta = (now_ts - dt).total_seconds()
                    except Exception:
                        continue
                if delta <= 30:
                    continue
                lost_tasks = [
                    tid
                    for tid, claim in self._pending_claims.items()
                    if claim.get("worker_id") == worker_id and claim.get("claimed")
                ]
                for task_id in lost_tasks:
                    del self._pending_claims[task_id]
                    try:
                        if self._state is not None:
                            self._state.requeue(task_id)
                    except Exception:
                        pass
                del self._worker_stats[worker_id]
                try:
                    if self._run_view is not None:
                        getattr(self._run_view, "on_worker_disconnected")(worker_id)
                except Exception:
                    pass
                # Always deregister workers that have gone silent so new controllers
                # don't try to dispatch to ghost nodes from old runs.
                try:
                    await self.registry.deregister(worker_id)
                except Exception:
                    pass
                await self.bus.publish(
                    create_bus_message(
                        topic=NODE_LEFT,
                        payload={
                            "node_id": worker_id,
                            "lost_task_count": len(lost_tasks),
                        },
                        sender_id=self.node_id,
                        run_id=self.run_id,
                    )
                )
                self._dispatch_wakeup.set()

    async def heartbeat_monitor(self) -> None:
        """
        Controller heartbeat loop (leader only).
        In single-node mode (InMemoryBus), this keeps the loop alive and provides a hook
        for future controller-side liveness signals. In distributed mode, workers send
        heartbeats; controller does not need to broadcast its own heartbeat for scheduling.
        """
        while self._is_leader:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _on_status_request(self, msg: object) -> None:
        payload = await self.get_status()
        await self.bus.publish(
            create_bus_message(
                topic=SWARM_STATUS_RESPONSE,
                payload=payload,
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )

    async def get_status(self) -> dict:
        tasks = self.scheduler.get_all_tasks()
        completed = sum(1 for t in tasks if t.status.value == 2)
        failed = sum(1 for t in tasks if t.status.value == -1)
        pending = sum(1 for t in tasks if t.status.value == 0)
        workers = await self.registry.get_workers()
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "is_leader": self._is_leader,
            "scheduler": {
                "total": len(tasks),
                "completed": completed,
                "failed": failed,
                "pending": pending,
            },
            "workers": [w.to_dict() for w in workers],
            "worker_stats": dict(self._worker_stats),
            "uptime_seconds": time.monotonic() - self._started_at,
        }


def _make_node_id() -> str:
    from uuid import uuid4
    return str(uuid4())
