import time
import pytest
from devsper.peers.raft import RaftState, RaftRole, RaftHeartbeat, RaftVote, ELECTION_TIMEOUT_MAX


def make_raft(node_id="n1", subgraph_id="sg1") -> RaftState:
    return RaftState(node_id=node_id, subgraph_id=subgraph_id)


def test_initial_state_is_follower():
    raft = make_raft()
    assert raft.role == RaftRole.FOLLOWER
    assert raft.current_term == 0
    assert raft.leader_id is None


def test_heartbeat_received_updates_leader():
    raft = make_raft()
    hb = RaftHeartbeat(term=1, leader_id="n2", subgraph_id="sg1")
    raft.heartbeat_received(hb)
    assert raft.leader_id == "n2"
    assert raft.current_term == 1


def test_stale_heartbeat_ignored():
    raft = make_raft()
    raft.current_term = 5
    hb = RaftHeartbeat(term=3, leader_id="n2", subgraph_id="sg1")
    raft.heartbeat_received(hb)
    assert raft.leader_id is None  # stale heartbeat not applied


def test_vote_granted_first_time():
    raft = make_raft()
    vote = RaftVote(term=1, candidate_id="n2", subgraph_id="sg1")
    assert raft.vote_requested(vote) is True
    assert raft.voted_for == "n2"


def test_vote_denied_already_voted():
    raft = make_raft()
    raft.vote_requested(RaftVote(term=1, candidate_id="n2", subgraph_id="sg1"))
    result = raft.vote_requested(RaftVote(term=1, candidate_id="n3", subgraph_id="sg1"))
    assert result is False


def test_become_leader():
    raft = make_raft()
    raft.current_term = 1
    raft.become_leader()
    assert raft.is_leader is True
    assert raft.leader_id == "n1"


def test_leader_stepdown_after_missed_heartbeats():
    raft = make_raft()
    raft.become_leader()
    from devsper.peers.raft import HEARTBEAT_MISS_LIMIT
    for _ in range(HEARTBEAT_MISS_LIMIT):
        raft.tick()
    assert raft.role == RaftRole.FOLLOWER


def test_election_triggered_after_timeout():
    raft = make_raft()
    # Force last_heartbeat to be far in the past
    raft._last_heartbeat = time.monotonic() - ELECTION_TIMEOUT_MAX - 1
    should_elect = raft.tick()
    assert should_elect is True
    assert raft.role == RaftRole.CANDIDATE
