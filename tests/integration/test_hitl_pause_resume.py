import asyncio

import pytest

from devsper.core.hitl.state_machine import HITLCoordinator
from devsper.runtime.clarification_manager import ClarificationManager
from devsper.events import ClarificationRequest, ClarificationField


def test_hitl_coordinator_resume_is_idempotent():
    coord = HITLCoordinator()
    s1 = coord.request_input(request_id="req-1", task_id="task-1")
    assert s1.state.value == "awaiting_input"

    s2 = coord.resume("req-1")
    assert s2 is not None
    assert s2.state.value == "resumed"

    # Duplicate resume should not create a second session or crash.
    s3 = coord.resume("req-1")
    assert s3 is not None
    assert s3.state.value == "resumed"


@pytest.mark.asyncio
async def test_clarification_manager_submit_is_deduped_by_request_id():
    manager = ClarificationManager(timeout_seconds=2)
    called = []
    ready_started = asyncio.Event()
    finish = asyncio.Event()

    async def on_ready(q):
        called.append(q.request.request_id)
        ready_started.set()
        await finish.wait()
        manager.resolve(q.request.request_id, {"q": "a"})

    manager.on_clarification_ready = on_ready
    dispatch_task = asyncio.create_task(manager.run_dispatch_loop())

    req = ClarificationRequest(
        request_id="dup-req",
        task_id="t1",
        agent_role="agent",
        fields=[
            ClarificationField(
                type="text",
                question="q",
                options=None,
                default=None,
                required=True,
            )
        ],
        context="ctx",
        priority=1,
        timeout_seconds=1,
    )

    # Submit the same request twice concurrently.
    t1 = asyncio.create_task(manager.submit(req, node_id="n1"))
    await ready_started.wait()
    t2 = asyncio.create_task(manager.submit(req, node_id="n1"))

    await asyncio.sleep(0.05)
    finish.set()
    r1, r2 = await asyncio.gather(t1, t2)

    assert called == ["dup-req"]
    assert r1.request_id == "dup-req"
    assert r2.request_id == "dup-req"
    assert r1.skipped is False
    assert r2.skipped is False

    dispatch_task.cancel()

