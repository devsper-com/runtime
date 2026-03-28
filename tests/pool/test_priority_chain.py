import asyncio

from devsper.pool.models import PoolTier, QueuedTask, WorkerRecord, WorkerStatus
from tests.pool.fixtures import make_pool


def test_priority_chain_dedicated_beats_global():
    async def run():
        pool = await make_pool()
        # global idle worker
        gw = WorkerRecord(worker_id="g1", node_id="n1", org_id=None, tier=PoolTier.GLOBAL, status=WorkerStatus.IDLE)
        # dedicated idle worker for org_a
        dw = WorkerRecord(worker_id="d1", node_id="n2", org_id="org_a", tier=PoolTier.DEDICATED, status=WorkerStatus.IDLE)
        await pool.register_worker(gw)
        await pool.register_worker(dw)
        t = QueuedTask(task_id="t1", org_id="org_a", user_id="u1", priority=10, payload_enc=b"\x01\x02")
        assigned = await pool.enqueue(t)
        assert assigned == "d1"
        assert pool.bus.published[-1][0] == "devsper:worker:d1"

    asyncio.run(run())


def test_org_isolation_org_b_task_not_to_org_a_dedicated():
    async def run():
        pool = await make_pool()
        dw = WorkerRecord(worker_id="d1", node_id="n2", org_id="org_a", tier=PoolTier.DEDICATED, status=WorkerStatus.IDLE)
        gw = WorkerRecord(worker_id="g1", node_id="n1", org_id=None, tier=PoolTier.GLOBAL, status=WorkerStatus.IDLE)
        await pool.register_worker(dw)
        await pool.register_worker(gw)
        t = QueuedTask(task_id="t1", org_id="org_b", user_id="u1", priority=10, payload_enc=b"\x01")
        assigned = await pool.enqueue(t)
        assert assigned == "g1"

    asyncio.run(run())

