"""
PeerNode: replaces Controller + Worker as the fundamental execution unit.
Any PeerNode can be elected leader for a subgraph via Raft-lite.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from devsper.compiler.ir import GraphSpec
from devsper.graph.runtime import GraphRuntime
from devsper.graph.state import AgentState, initial_state
from devsper.graph.mutations import MutationRequest, MutationValidator
from devsper.peers.raft import RaftState, RaftHeartbeat, RaftVote, HEARTBEAT_INTERVAL
from devsper.peers.ownership import SubgraphOwnership
from devsper.peers.sync import publish_state_snapshot

logger = logging.getLogger(__name__)


@dataclass
class PeerNode:
    """
    Leaderless distributed execution unit.

    Each PeerNode:
    - Registers its capabilities
    - Participates in Raft-lite elections per subgraph
    - Executes subgraphs when elected leader
    - Publishes state snapshots for failover
    """

    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    capabilities: list[str] = field(default_factory=list)

    # injected by caller
    bus: object = field(default=None, repr=False)
    ownership: SubgraphOwnership = field(default_factory=SubgraphOwnership)
    mutation_validator: MutationValidator = field(default_factory=MutationValidator)

    # internal state
    _raft_states: dict[str, RaftState] = field(default_factory=dict, init=False, repr=False)
    _runtime: GraphRuntime = field(default_factory=GraphRuntime, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _heartbeat_task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        """Start the peer node (connect bus, begin heartbeat loop)."""
        self._running = True
        if self.bus is not None:
            await self.bus.start()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("PeerNode[%s] started (capabilities=%s)", self.node_id, self.capabilities)

    async def stop(self) -> None:
        """Stop the peer node."""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.bus is not None:
            await self.bus.stop()
        logger.info("PeerNode[%s] stopped", self.node_id)

    async def execute_subgraph(
        self,
        spec: GraphSpec,
        state: AgentState | None = None,
        subgraph_id: str = "",
    ) -> AgentState:
        """
        Execute a subgraph as the elected leader.
        Publishes state snapshots via bus after each significant step.
        """
        subgraph_id = subgraph_id or spec.version
        if not self.ownership.claim(subgraph_id, self.node_id):
            raise RuntimeError(
                f"PeerNode[{self.node_id}] could not claim subgraph {subgraph_id} "
                f"(owned by {self.ownership.leader_of(subgraph_id)})"
            )

        if state is None:
            state = initial_state(task="")

        logger.info("PeerNode[%s] executing subgraph %s", self.node_id, subgraph_id)
        try:
            result = self._runtime.run_spec(spec, state=state)
            if self.bus is not None:
                await publish_state_snapshot(
                    bus=self.bus,
                    run_id=result.get("run_id", ""),
                    subgraph_id=subgraph_id,
                    state=result,
                    sender_id=self.node_id,
                )
            return result
        finally:
            self.ownership.release(subgraph_id, self.node_id)

    async def propose_mutation(self, req: MutationRequest, spec: GraphSpec) -> bool:
        """
        Propose a graph mutation. In a real cluster this would go through Raft consensus.
        In the current implementation: validate locally, accept if valid.
        """
        if not self.mutation_validator.validate(req, spec):
            logger.debug("PeerNode[%s] rejected mutation %s", self.node_id, req.op)
            return False
        logger.info("PeerNode[%s] accepted mutation %s: %s", self.node_id, req.op, req.justification)
        return True

    def _ensure_raft(self, subgraph_id: str) -> RaftState:
        if subgraph_id not in self._raft_states:
            self._raft_states[subgraph_id] = RaftState(self.node_id, subgraph_id)
        return self._raft_states[subgraph_id]

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats for owned subgraphs; tick election timers for others."""
        while self._running:
            try:
                for subgraph_id, raft in list(self._raft_states.items()):
                    if raft.is_leader:
                        hb = RaftHeartbeat(
                            term=raft.current_term,
                            leader_id=self.node_id,
                            subgraph_id=subgraph_id,
                        )
                        if self.bus is not None:
                            try:
                                from devsper.bus.message import create_bus_message
                                await self.bus.publish(create_bus_message(
                                    topic=f"peers.heartbeat.{subgraph_id}",
                                    payload={"term": hb.term, "leader_id": hb.leader_id},
                                    sender_id=self.node_id,
                                    run_id="",
                                ))
                            except Exception:
                                raft.ack_heartbeat()  # local ack as fallback
                        else:
                            raft.ack_heartbeat()
                    else:
                        should_elect = raft.tick()
                        if should_elect:
                            logger.debug("PeerNode[%s] starting election for %s", self.node_id, subgraph_id)
                            # In a single-node setup, immediately win the election
                            raft.current_term += 1
                            raft.become_leader()
                            self.ownership.claim(subgraph_id, self.node_id)
            except Exception:
                logger.exception("PeerNode[%s]: error in heartbeat loop", self.node_id)
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    @property
    def owned_subgraphs(self) -> set[str]:
        return self.ownership.owned_by(self.node_id)
