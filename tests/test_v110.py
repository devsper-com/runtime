"""Tests for v1.10 distribution: single-node, cluster types, router, state backend."""

import asyncio
import pytest

from devsper.cluster.node_info import NodeInfo, NodeRole, ClusterState
from devsper.cluster.local import InMemoryRegistry, LocalLeaderElector
from devsper.cluster.state_backend import FilesystemStateBackend
from devsper.cluster.router import TaskRouter
from devsper.types.task import Task, TaskStatus


def test_single_node_no_redis_required():
    """Swarm with config nodes.mode=single runs without Redis installed or configured."""
    from devsper.swarm.swarm import Swarm
    from devsper.utils.event_logger import EventLog
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex
    from devsper.config import get_config
    event_log = EventLog(events_folder_path=".devsper/events")
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    cfg = get_config()
    cfg.nodes.mode = "single"
    swarm = Swarm(
        config=cfg,
        worker_count=2,
        worker_model="mock",
        planner_model="mock",
        event_log=event_log,
        memory_router=memory_router,
        use_tools=False,
    )
    result = swarm.run("Hello")
    assert isinstance(result, dict)
    assert len(result) >= 1
    for v in result.values():
        assert isinstance(v, str)


def test_single_node_results_identical():
    """Same task on single-node produces same structure as pre-v1.10 result dict."""
    from devsper.swarm.swarm import Swarm
    from devsper.utils.event_logger import EventLog
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex
    from devsper.config import get_config
    event_log = EventLog(events_folder_path=".devsper/events")
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )
    cfg = get_config()
    cfg.nodes.mode = "single"
    swarm = Swarm(
        config=cfg,
        worker_count=2,
        worker_model="mock",
        planner_model="mock",
        event_log=event_log,
        memory_router=memory_router,
        use_tools=False,
    )
    result = swarm.run("Say hi")
    assert isinstance(result, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in result.items())


def test_node_info_roundtrip():
    """NodeInfo to_dict/from_dict roundtrip."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    n = NodeInfo(
        node_id="n1",
        role=NodeRole.WORKER,
        host="localhost",
        rpc_port=7701,
        rpc_url="http://localhost:7701",
        tags=["gpu"],
        max_workers=4,
        joined_at=now,
        last_heartbeat=now,
        version="1.10.0",
    )
    d = n.to_dict()
    n2 = NodeInfo.from_dict(d)
    assert n2.node_id == n.node_id
    assert n2.role == n.role
    assert n2.max_workers == n.max_workers


def test_in_memory_registry():
    """InMemoryRegistry register/get_all/get_workers."""
    async def _run():
        reg = InMemoryRegistry("run1")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        node = NodeInfo(
            node_id="w1",
            role=NodeRole.WORKER,
            host="h",
            rpc_port=7701,
            rpc_url="http://h:7701",
            tags=[],
            max_workers=2,
            joined_at=now,
            last_heartbeat=now,
            version="1.10",
        )
        await reg.register(node)
        all_n = await reg.get_all()
        assert len(all_n) == 1
        assert all_n[0].node_id == "w1"
        workers = await reg.get_workers()
        assert len(workers) == 1

    asyncio.run(_run())


def test_local_leader_elector():
    """LocalLeaderElector first campaigner wins."""
    async def _run():
        elector = LocalLeaderElector("run1")
        won = await elector.campaign("node-a")
        assert won is True
        assert await elector.get_leader() == "node-a"
        won2 = await elector.campaign("node-b")
        assert won2 is False
        assert await elector.refresh("node-a") is True
        assert await elector.refresh("node-b") is False

    asyncio.run(_run())


def test_filesystem_state_backend(tmp_path):
    """FilesystemStateBackend save/load/list."""
    async def _run():
        backend = FilesystemStateBackend(str(tmp_path))
        await backend.save_snapshot("run1", {"a": 1, "tasks": []})
        snap = await backend.load_snapshot("run1")
        assert snap is not None
        assert snap["a"] == 1
        listed = await backend.list_snapshots()
        assert "run1" in listed
        await backend.delete_snapshot("run1")
        assert await backend.load_snapshot("run1") is None

    asyncio.run(_run())


def test_task_routing_prefers_low_load():
    """All else equal, router picks worker with lower active_tasks * avg_duration."""
    router = TaskRouter("1.10.0")
    task = Task(id="t1", description="d", dependencies=[])
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    w_light = NodeInfo("w1", NodeRole.WORKER, "h", 7701, "http://h:7701", [], 4, now, now, "1.10.0")
    w_heavy = NodeInfo("w2", NodeRole.WORKER, "h", 7702, "http://h:7702", [], 4, now, now, "1.10.0")
    stats = {
        "w1": {"active_tasks": 0, "avg_task_duration_seconds": 1.0, "cached_tools": [], "completed_task_ids": []},
        "w2": {"active_tasks": 3, "avg_task_duration_seconds": 10.0, "cached_tools": [], "completed_task_ids": []},
    }
    chosen = router.route(task, [w_light, w_heavy], stats)
    assert chosen is not None
    assert chosen.node_id == "w1"


def test_version_incompatible_worker_excluded():
    """Worker with mismatched major version not routed any tasks."""
    router = TaskRouter("1.10.0")
    task = Task(id="t1", description="d", dependencies=[])
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    w_old = NodeInfo("w1", NodeRole.WORKER, "h", 7701, "http://h:7701", [], 4, now, now, "2.0.0")
    w_ok = NodeInfo("w2", NodeRole.WORKER, "h", 7702, "http://h:7702", [], 4, now, now, "1.10.0")
    stats = {}
    chosen = router.route(task, [w_old, w_ok], stats)
    assert chosen is not None
    assert chosen.node_id == "w2"
