from devsper.peers.ownership import SubgraphOwnership


def test_claim_succeeds_when_free():
    o = SubgraphOwnership()
    assert o.claim("sg1", "node_a") is True
    assert o.leader_of("sg1") == "node_a"


def test_claim_fails_when_taken_by_other():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    assert o.claim("sg1", "node_b") is False


def test_claim_succeeds_by_same_node():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    assert o.claim("sg1", "node_a") is True


def test_release_by_owner():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    assert o.release("sg1", "node_a") is True
    assert o.leader_of("sg1") is None


def test_release_by_non_owner_fails():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    assert o.release("sg1", "node_b") is False
    assert o.leader_of("sg1") == "node_a"


def test_transfer_leadership():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    assert o.transfer("sg1", "node_a", "node_b") is True
    assert o.leader_of("sg1") == "node_b"


def test_owned_by_returns_correct_set():
    o = SubgraphOwnership()
    o.claim("sg1", "node_a")
    o.claim("sg2", "node_a")
    o.claim("sg3", "node_b")
    owned = o.owned_by("node_a")
    assert owned == {"sg1", "sg2"}
