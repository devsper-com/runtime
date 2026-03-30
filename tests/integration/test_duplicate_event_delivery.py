import asyncio

import pytest

from devsper.events import ClarificationField, ClarificationRequest
from devsper.runtime.clarification_manager import ClarificationManager


@pytest.mark.asyncio
async def test_duplicate_event_delivery_is_deduped_for_hitl_requests():
    manager = ClarificationManager(timeout_seconds=2)
    activated = []
    proceed = asyncio.Event()

    async def on_ready(q):
        activated.append(q.request.request_id)
        await proceed.wait()
        manager.resolve(q.request.request_id, {"q": "ok"})

    manager.on_clarification_ready = on_ready
    dispatch_task = asyncio.create_task(manager.run_dispatch_loop())

    req = ClarificationRequest(
        request_id="dup-1",
        task_id="t-1",
        agent_role="agent",
        fields=[
            ClarificationField(type="text", question="q", options=None, default=None, required=True),
        ],
        context="ctx",
        timeout_seconds=2,
    )

    t1 = asyncio.create_task(manager.submit(req, node_id="worker-a"))
    t2 = asyncio.create_task(manager.submit(req, node_id="worker-a"))
    await asyncio.sleep(0.1)
    proceed.set()
    r1, r2 = await asyncio.gather(t1, t2)

    assert activated == ["dup-1"]
    assert r1.request_id == "dup-1"
    assert r2.request_id == "dup-1"

    dispatch_task.cancel()

