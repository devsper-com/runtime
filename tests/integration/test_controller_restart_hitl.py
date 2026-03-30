from devsper.core.runtime.durability import ClarificationStore, RunStateStore


def test_controller_restart_hitl_pending_clarifications_restore():
    clar_store = ClarificationStore()
    run_store = RunStateStore()

    snapshot = {"run_id": "run-1", "tasks": []}
    pending = {
        "req-1": {
            "request": {
                "request_id": "req-1",
                "task_id": "task-1",
                "agent_role": "agent",
                "fields": [],
                "context": "Need user input",
                "priority": 1,
                "timeout_seconds": 120,
            },
            "node_id": "worker-1",
        }
    }
    run_state = {
        "pause_state": {"waiting_task_ids": ["task-1"]},
        "active_assignments": {"pending_claims": {"task-1": {"worker_id": "worker-1"}}},
    }

    clar_store.save(snapshot, pending)
    run_store.save(snapshot, run_state)

    restored_pending = clar_store.load(snapshot)
    restored_state = run_store.load(snapshot)

    assert "req-1" in restored_pending
    assert restored_pending["req-1"]["request"]["task_id"] == "task-1"
    assert restored_state["pause_state"]["waiting_task_ids"] == ["task-1"]

