"""
State sync across peers via message bus.
AgentState snapshots are published after each node completion so any peer
can resume a failed subgraph from the last known-good state.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from devsper.bus.backends.base import BusBackend
from devsper.bus.message import create_bus_message
from devsper.graph.state import AgentState

logger = logging.getLogger(__name__)

TOPIC_STATE_SNAPSHOT = "peers.state_snapshot"
TOPIC_MUTATION_PROPOSAL = "peers.mutation_proposal"


async def publish_state_snapshot(
    bus: BusBackend,
    run_id: str,
    subgraph_id: str,
    state: AgentState,
    sender_id: str,
) -> None:
    """Publish an AgentState snapshot so any peer can resume if this node fails."""
    payload = {
        "subgraph_id": subgraph_id,
        "state": {
            "task": state.get("task", ""),
            "run_id": state.get("run_id", run_id),
            "results": state.get("results", {}),
            "completed_nodes": state.get("completed_nodes", []),
            "pending_mutations": state.get("pending_mutations", []),
            "graph_spec": state.get("graph_spec", {}),
            "budget_used": state.get("budget_used", 0.0),
            "messages": [],  # omit from snapshot (can be large)
        },
    }
    msg = create_bus_message(
        topic=TOPIC_STATE_SNAPSHOT,
        payload=payload,
        sender_id=sender_id,
        run_id=run_id,
    )
    await bus.publish(msg)


async def subscribe_state_snapshots(
    bus: BusBackend,
    handler: Callable[[str, str, AgentState], Awaitable[None]],
) -> None:
    """
    Subscribe to AgentState snapshots from peers.
    Handler receives (run_id, subgraph_id, state).
    """
    async def _on_message(msg):
        payload = msg.payload or {}
        subgraph_id = payload.get("subgraph_id", "")
        raw_state = payload.get("state", {})
        from devsper.graph.state import initial_state
        state = initial_state(
            task=raw_state.get("task", ""),
            run_id=raw_state.get("run_id", msg.run_id),
        )
        state.update(raw_state)
        try:
            await handler(msg.run_id, subgraph_id, state)
        except Exception:
            logger.exception("sync: error in state snapshot handler")

    await bus.subscribe(TOPIC_STATE_SNAPSHOT, _on_message)
