"""
Controller node: dispatch logic, cluster state, leader election.
Distributed mode only; requires redis, fastapi, uvicorn.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from hivemind.bus.message import create_bus_message
from hivemind.bus.topics import (
    TASK_READY,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_CLAIMED,
    TASK_CLAIM_GRANTED,
    TASK_CLAIM_REJECTED,
    NODE_HEARTBEAT,
    NODE_JOINED,
    NODE_LEFT,
    NODE_BECAME_LEADER,
    NODE_LOST_LEADERSHIP,
    SWARM_SNAPSHOT,
    SWARM_STATUS_REQUEST,
    SWARM_STATUS_RESPONSE,
)
from hivemind.agents.agent import AgentResponse
from hivemind.cluster.node_info import NodeInfo, NodeRole
from hivemind.cluster.registry import ClusterRegistry
from hivemind.cluster.election import LeaderElector
from hivemind.cluster.state_backend import StateBackend
from hivemind.cluster.router import TaskRouter
from hivemind.swarm.scheduler import Scheduler

log = logging.getLogger(__name__)


def _require_distributed() -> None:
    try:
        import redis.asyncio  # noqa: F401
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "Distributed mode requires: pip install hivemind-ai[distributed]"
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

    async def start(self) -> None:
        await self.registry.register(self.node_info)
        await self.bus.subscribe(TASK_COMPLETED, self._on_task_completed)
        await self.bus.subscribe(TASK_FAILED, self._on_task_failed)
        await self.bus.subscribe(TASK_CLAIMED, self._on_task_claimed)
        await self.bus.subscribe(NODE_HEARTBEAT, self._on_heartbeat)
        await self.bus.subscribe(NODE_JOINED, self._on_node_joined)
        await self.bus.subscribe(SWARM_STATUS_REQUEST, self._on_status_request)
        asyncio.create_task(self._registry_heartbeat_loop())
        asyncio.create_task(
            self.elector.watch(
                self.node_id,
                self._become_leader,
                self._lose_leadership,
            )
        )

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
        snapshot = await self.state_backend.load_snapshot(self.run_id)
        if snapshot:
            self.scheduler = Scheduler.restore(snapshot)
            log.info(
                "Restored scheduler from snapshot: %s tasks already done",
                snapshot.get("completed_count", 0),
            )
        self._leader_tasks = [
            asyncio.create_task(self.dispatch_loop()),
            asyncio.create_task(self.checkpoint_loop()),
            asyncio.create_task(self.heartbeat_monitor()),
            asyncio.create_task(self.worker_timeout_monitor()),
        ]
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
        await self.bus.publish(
            create_bus_message(
                topic=NODE_LOST_LEADERSHIP,
                payload={"node_id": self.node_id},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )

    async def dispatch_loop(self) -> None:
        timeout_sec = 120
        nodes_cfg = getattr(self.config, "nodes", None)
        if nodes_cfg:
            timeout_sec = getattr(nodes_cfg, "task_claim_timeout_seconds", 120)
        while not self.scheduler.is_finished():
            if not self._is_leader:
                break
            ready = self.scheduler.get_ready_tasks()
            workers = await self.registry.get_workers()
            now_ts = time.monotonic()
            for task in ready:
                if task.id in self._pending_claims:
                    pending = self._pending_claims[task.id]
                    if (now_ts - pending.get("dispatched_at", 0)) > timeout_sec:
                        del self._pending_claims[task.id]
                        log.warning("Task %s claim timed out, re-queuing", task.id)
                    continue
                worker = self.router.route(task, workers, self._worker_stats)
                if worker is None:
                    continue
                # Add before publish so _on_task_claimed sees the entry when worker replies immediately
                self._pending_claims[task.id] = {
                    "dispatched_at": now_ts,
                    "target_worker": worker.node_id,
                    "claimed": False,
                }
                await self.bus.publish(
                    create_bus_message(
                        topic=TASK_READY,
                        payload={
                            **task.to_dict(),
                            "target_worker_id": worker.node_id,
                        },
                        sender_id=self.node_id,
                        run_id=self.run_id,
                    )
                )
            await asyncio.sleep(0.05)

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
        await self.bus.publish(
            create_bus_message(
                topic=TASK_CLAIM_GRANTED,
                payload={"task_id": task_id, "worker_id": worker_id},
                sender_id=self.node_id,
                run_id=self.run_id,
            )
        )

    async def _on_task_completed(self, msg: object) -> None:
        payload = getattr(msg, "payload", {}) or {}
        sender_id = getattr(msg, "sender_id", "")
        try:
            response = AgentResponse.from_dict(payload)
        except Exception:
            return
        self.scheduler.mark_completed(response.task_id, response.result)
        self._pending_claims.pop(response.task_id, None)
        if sender_id and sender_id not in self._worker_stats:
            self._worker_stats[sender_id] = {}
        if sender_id:
            self._worker_stats[sender_id].setdefault("completed_task_ids", [])
            self._worker_stats[sender_id]["completed_task_ids"] = (
                self._worker_stats[sender_id]["completed_task_ids"][-49:]
                + [response.task_id]
            )
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
            self.scheduler.mark_failed(task_id, error)
            self._pending_claims.pop(task_id, None)

    async def _on_heartbeat(self, msg: object) -> None:
        sender_id = getattr(msg, "sender_id", "")
        payload = getattr(msg, "payload", {}) or {}
        if not sender_id:
            return
        self._worker_stats[sender_id] = dict(payload)
        self._worker_stats[sender_id]["last_seen"] = datetime.now(timezone.utc)
        try:
            await self.registry.heartbeat(
                sender_id, {"last_heartbeat": datetime.now(timezone.utc).isoformat()}
            )
        except Exception:
            pass

    async def _on_node_joined(self, msg: object) -> None:
        if not self._is_leader:
            return
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
                del self._worker_stats[worker_id]
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
