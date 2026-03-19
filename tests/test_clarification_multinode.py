import asyncio
from dataclasses import dataclass

import pytest

from devsper.events import ClarificationField, ClarificationRequest, ClarificationResponse
from devsper.runtime.clarification_manager import ClarificationManager, QueuedClarification


@pytest.mark.asyncio
async def test_clarification_manager_serializes_requests():
    manager = ClarificationManager()
    active_lock = asyncio.Lock()
    seen = []

    async def on_ready(q: QueuedClarification):
        # ensure not concurrent
        assert not active_lock.locked()
        async with active_lock:
            seen.append(q.request.request_id)
            # auto-resolve
            manager.resolve(q.request.request_id, {"ok": q.request.request_id})

    manager.on_clarification_ready = on_ready
    asyncio.create_task(manager.run_dispatch_loop())

    reqs = [
        ClarificationRequest(
            request_id=f"r{i}",
            task_id="t",
            agent_role="agent",
            fields=[ClarificationField(type="text", question="q", options=None, default=None, required=True)],
            context="ctx",
        )
        for i in range(3)
    ]
    resps = await asyncio.gather(*[manager.submit(r, node_id="n") for r in reqs])
    assert [r.request_id for r in resps] == ["r0", "r1", "r2"]
    assert seen == ["r0", "r1", "r2"]


@pytest.mark.asyncio
async def test_clarification_manager_queue_order_priority():
    manager = ClarificationManager()
    order = []

    async def on_ready(q: QueuedClarification):
        order.append(q.request.request_id)
        manager.resolve(q.request.request_id, {})

    manager.on_clarification_ready = on_ready
    asyncio.create_task(manager.run_dispatch_loop())

    low = ClarificationRequest(
        request_id="p1",
        task_id="t",
        agent_role="agent",
        fields=[],
        context="",
        priority=1,
        timeout_seconds=5,
    )
    high = ClarificationRequest(
        request_id="p0",
        task_id="t",
        agent_role="agent",
        fields=[],
        context="",
        priority=0,
        timeout_seconds=5,
    )
    await asyncio.gather(manager.submit(low), manager.submit(high))
    assert order[0] == "p0"


@pytest.mark.asyncio
async def test_clarification_manager_cancel_task_resolves_skipped():
    manager = ClarificationManager()

    called = False

    async def on_ready(q: QueuedClarification):
        nonlocal called
        called = True

    manager.on_clarification_ready = on_ready
    asyncio.create_task(manager.run_dispatch_loop())

    reqs = [
        ClarificationRequest(request_id=f"r{i}", task_id="task-1", agent_role="a", fields=[], context="")
        for i in range(3)
    ]
    tasks = [asyncio.create_task(manager.submit(r)) for r in reqs]
    await asyncio.sleep(0.05)
    manager.cancel_task("task-1")
    resps = await asyncio.gather(*tasks)
    assert all(isinstance(r, ClarificationResponse) for r in resps)
    assert all(r.skipped for r in resps)
    assert called is False


@pytest.mark.asyncio
async def test_clarification_manager_timeout_uses_defaults():
    manager = ClarificationManager(timeout_seconds=1)
    req = ClarificationRequest(
        request_id="tmo",
        task_id="t",
        agent_role="a",
        fields=[
            {"type": "text", "question": "x", "default": "Markdown", "options": None, "required": True},
        ],
        context="",
        timeout_seconds=0.1,
    )
    resp = await manager.submit(req, node_id="n")
    assert resp.skipped is True
    assert resp.answers.get("x") == "Markdown"


@pytest.mark.asyncio
async def test_new_request_while_active_queues():
    manager = ClarificationManager()
    started = asyncio.Event()
    finish = asyncio.Event()

    async def on_ready(q: QueuedClarification):
        if q.request.request_id == "A":
            started.set()
            await finish.wait()
            manager.resolve("A", {})
        else:
            manager.resolve(q.request.request_id, {})

    manager.on_clarification_ready = on_ready
    asyncio.create_task(manager.run_dispatch_loop())

    req_a = ClarificationRequest(request_id="A", task_id="t", agent_role="a", fields=[], context="")
    req_b = ClarificationRequest(request_id="B", task_id="t", agent_role="b", fields=[], context="")

    ta = asyncio.create_task(manager.submit(req_a))
    await started.wait()
    tb = asyncio.create_task(manager.submit(req_b))
    snap = manager.queue_snapshot()
    assert any(s["request_id"] == "B" and s["status"] == "queued" for s in snap)
    finish.set()
    await asyncio.gather(ta, tb)

