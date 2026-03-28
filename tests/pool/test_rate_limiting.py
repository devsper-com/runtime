import asyncio

import pytest

from devsper.pool.manager import RateLimitError
from devsper.pool.models import QueuedTask
from tests.pool.fixtures import make_pool


def test_rate_limiting_61st_rejected():
    async def run():
        pool = await make_pool()
        pool.config.max_tasks_per_minute = 60
        for i in range(60):
            await pool.enqueue(QueuedTask(task_id=f"t{i}", org_id="org", user_id="u", priority=1, payload_enc=b"x"))
        with pytest.raises(RateLimitError):
            await pool.enqueue(QueuedTask(task_id="t61", org_id="org", user_id="u", priority=1, payload_enc=b"x"))

    asyncio.run(run())

