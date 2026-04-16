import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.graph.state import initial_state
from devsper.graph.mutations import MutationRequest
from devsper.peers.node import PeerNode
from devsper.peers.ownership import SubgraphOwnership


def two_node_spec() -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="researcher", role="Research the topic"),
            NodeSpec(id="writer", role="Write the report"),
        ],
        edges=[EdgeSpec(src="researcher", dst="writer")],
    )


def test_peer_node_default_id():
    peer = PeerNode()
    assert len(peer.node_id) > 0


def test_peer_node_capabilities():
    peer = PeerNode(capabilities=["research", "writing"])
    assert "research" in peer.capabilities


@pytest.mark.asyncio
async def test_peer_node_start_stop():
    peer = PeerNode(node_id="test-peer", bus=None)
    await peer.start()
    assert peer._running is True
    await peer.stop()
    assert peer._running is False


@pytest.mark.asyncio
async def test_execute_subgraph_returns_state():
    peer = PeerNode(node_id="peer-1", bus=None)
    await peer.start()
    state = initial_state(task="research AI", run_id="run-1")
    result = await peer.execute_subgraph(two_node_spec(), state=state)
    assert "researcher" in result["completed_nodes"]
    assert "writer" in result["completed_nodes"]
    await peer.stop()


@pytest.mark.asyncio
async def test_execute_subgraph_releases_ownership():
    peer = PeerNode(node_id="peer-1", bus=None)
    await peer.start()
    spec = two_node_spec()
    await peer.execute_subgraph(spec)
    # After execution, ownership should be released
    assert peer.ownership.leader_of(spec.version) is None
    await peer.stop()


@pytest.mark.asyncio
async def test_propose_mutation_accepted():
    peer = PeerNode(node_id="peer-1", bus=None)
    spec = two_node_spec()
    req = MutationRequest(
        op="add_node",
        payload={"id": "editor", "role": "Editor"},
        justification="need editing step",
        confidence=0.9,
    )
    result = await peer.propose_mutation(req, spec)
    assert result is True


@pytest.mark.asyncio
async def test_propose_mutation_rejected_low_confidence():
    peer = PeerNode(node_id="peer-1", bus=None)
    spec = two_node_spec()
    req = MutationRequest(
        op="add_node",
        payload={"id": "editor", "role": "Editor"},
        justification="maybe",
        confidence=0.3,  # below threshold
    )
    result = await peer.propose_mutation(req, spec)
    assert result is False


@pytest.mark.asyncio
async def test_two_peers_cannot_claim_same_subgraph():
    shared_ownership = SubgraphOwnership()
    peer_a = PeerNode(node_id="peer-a", bus=None, ownership=shared_ownership)
    peer_b = PeerNode(node_id="peer-b", bus=None, ownership=shared_ownership)
    await peer_a.start()
    await peer_b.start()
    spec = two_node_spec()
    subgraph_id = "conflict-sg"
    shared_ownership.claim(subgraph_id, "peer-a")
    with pytest.raises(RuntimeError, match="could not claim"):
        await peer_b.execute_subgraph(spec, subgraph_id=subgraph_id)
    await peer_a.stop()
    await peer_b.stop()
