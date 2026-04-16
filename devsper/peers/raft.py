"""
Raft-lite: simplified leader election for subgraph ownership.

Design simplifications vs full Raft:
- Single-term elections (no log compaction, full log in bus)
- Leadership per subgraph, not per cluster
- Leader steps down if heartbeat missed × 3
- No persistent log on disk — state snapshots in bus/Redis are the source of truth

State machine: FOLLOWER → CANDIDATE → LEADER
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 0.5   # seconds between leader heartbeats
ELECTION_TIMEOUT_MIN = 1.5  # seconds
ELECTION_TIMEOUT_MAX = 3.0  # seconds
HEARTBEAT_MISS_LIMIT = 3    # steps down after this many missed heartbeats


class RaftRole(Enum):
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class RaftVote:
    term: int
    candidate_id: str
    subgraph_id: str


@dataclass
class RaftHeartbeat:
    term: int
    leader_id: str
    subgraph_id: str
    timestamp: float = field(default_factory=time.monotonic)


class RaftState:
    """
    Per-subgraph Raft state machine.
    Drives leader election for a single subgraph partition.
    """

    def __init__(self, node_id: str, subgraph_id: str) -> None:
        self.node_id = node_id
        self.subgraph_id = subgraph_id
        self.role = RaftRole.FOLLOWER
        self.current_term = 0
        self.voted_for: str | None = None
        self.leader_id: str | None = None
        self._last_heartbeat = time.monotonic()
        self._missed_heartbeats = 0
        self._on_leader_change: Callable[[str | None], Awaitable[None]] | None = None

    def set_leader_change_callback(self, cb: Callable[[str | None], Awaitable[None]]) -> None:
        self._on_leader_change = cb

    def heartbeat_received(self, hb: RaftHeartbeat) -> None:
        """Process incoming heartbeat from a leader."""
        if hb.term < self.current_term:
            return  # stale
        if hb.term > self.current_term:
            self.current_term = hb.term
            self.role = RaftRole.FOLLOWER
            self.voted_for = None
        self.leader_id = hb.leader_id
        self._last_heartbeat = time.monotonic()
        self._missed_heartbeats = 0

    def vote_requested(self, vote: RaftVote) -> bool:
        """
        Decide whether to grant a vote.
        Returns True if vote granted.
        """
        if vote.term < self.current_term:
            return False
        if vote.term > self.current_term:
            self.current_term = vote.term
            self.voted_for = None
            self.role = RaftRole.FOLLOWER
        if self.voted_for is None or self.voted_for == vote.candidate_id:
            self.voted_for = vote.candidate_id
            self._last_heartbeat = time.monotonic()  # reset timeout
            return True
        return False

    def tick(self) -> bool:
        """
        Called periodically. Returns True if this node should start an election.
        Also handles leader step-down on missed heartbeats.
        """
        now = time.monotonic()
        if self.role == RaftRole.LEADER:
            self._missed_heartbeats += 1
            if self._missed_heartbeats >= HEARTBEAT_MISS_LIMIT:
                logger.warning(
                    "RaftState[%s/%s]: leader stepping down after %d missed acks",
                    self.node_id, self.subgraph_id, self._missed_heartbeats,
                )
                self.role = RaftRole.FOLLOWER
                self.leader_id = None
            return False
        if self.role == RaftRole.FOLLOWER:
            import random
            timeout = random.uniform(ELECTION_TIMEOUT_MIN, ELECTION_TIMEOUT_MAX)
            if now - self._last_heartbeat > timeout:
                self.role = RaftRole.CANDIDATE
                return True
        return False

    def become_leader(self) -> None:
        self.role = RaftRole.LEADER
        self.leader_id = self.node_id
        self._missed_heartbeats = 0
        logger.info("RaftState[%s/%s]: became leader (term %d)", self.node_id, self.subgraph_id, self.current_term)

    def ack_heartbeat(self) -> None:
        """Called when leader receives an ack from a follower."""
        self._missed_heartbeats = max(0, self._missed_heartbeats - 1)

    @property
    def is_leader(self) -> bool:
        return self.role == RaftRole.LEADER
