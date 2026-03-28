import asyncio

from devsper.pool.models import PoolTier, QueuedTask, WorkerRecord, WorkerStatus
from tests.pool.fixtures import BusStub, PoolTestConfig
from devsper.pool.manager import PoolManager
from devsper.pool.store import InMemoryPoolStore


def test_dead_worker_marked_offline_and_task_requeues():
    async def run():
        store = InMemoryPoolStore()
        bus = BusStub()
        cfg = PoolTestConfig(profile="local", max_tasks_per_minute=1000, worker_timeout_secs=1)
        pool = PoolManager(store=store, bus=bus, config=cfg)

        w1 = WorkerRecord(worker_id="w1", node_id="n1", org_id=None, tier=PoolTier.GLOBAL, status=WorkerStatus.IDLE)
        w2 = WorkerRecord(worker_id="w2", node_id="n2", org_id=None, tier=PoolTier.GLOBAL, status=WorkerStatus.IDLE)
        await pool.register_worker(w1)
        await pool.register_worker(w2)
        await store.heartbeat("w1", ttl_secs=1)
        await store.heartbeat("w2", ttl_secs=90)

        # Assign a task
        assigned = await pool.enqueue(QueuedTask(task_id="t1", org_id="org", user_id="u", priority=10, payload_enc=b"aa"))
        assert assigned == "w1"
        # Let heartbeat expire
        await asyncio.sleep(1.2)
        assert not await store.is_alive("w1")

        # Pool notices expiry -> offline + requeue -> assign to w2
        await pool.evict_dead_workers()
        assert (await store.get_worker("w1")).status == WorkerStatus.OFFLINE
        # last published assignment should target w2
        assert bus.published[-1][0] == "devsper:worker:w2"

    asyncio.run(run())

