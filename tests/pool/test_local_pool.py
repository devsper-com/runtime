import asyncio

from devsper.pool.local_pool import LocalWorkerPool
from devsper.pool.models import QueuedTask
from tests.pool.fixtures import BusStub, PoolTestConfig
from devsper.pool.manager import PoolManager
from devsper.pool.store import InMemoryPoolStore


def test_local_pool_spawns_registers_and_accepts_task(tmp_path):
    async def run():
        store = InMemoryPoolStore()
        bus = BusStub()
        cfg = PoolTestConfig(profile="local")
        # use a long-running command for tests
        cfg.local_workers = 2
        cfg.local_worker_cmd = "python -c 'import time; time.sleep(30)'"
        pool = PoolManager(store=store, bus=bus, config=cfg)
        lp = LocalWorkerPool(pool, cfg, redis_url="redis://127.0.0.1:6379")
        await lp.start()
        # allow monitor heartbeat to tick once
        await asyncio.sleep(0.2)
        # enqueue should resolve to local worker
        wid = await pool.enqueue(QueuedTask(task_id="t1", org_id="org", user_id="u", priority=5, payload_enc=b"aa"))
        assert wid != "queued"
        assert bus.published, "expected publish to worker channel"
        await lp.stop()

    asyncio.run(run())

