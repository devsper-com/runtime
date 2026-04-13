import pytest
from devsper.marketplace.registry import CapabilityRegistry, AgentCapability
from devsper.marketplace.vectors import embed, cosine_similarity
from devsper.marketplace.matcher import match
from devsper.marketplace.auction import bid, assign_to_spec, coalition, AuctionResult
from devsper.compiler.ir import GraphSpec


# --- Capability vector tests ---

def test_embed_returns_list_of_floats():
    vec = embed("research quantum computing trends")
    assert isinstance(vec, list)
    assert all(isinstance(v, float) for v in vec)
    assert len(vec) > 0


def test_cosine_similarity_identical():
    vec = embed("research agent")
    assert cosine_similarity(vec, vec) > 0.99


def test_cosine_similarity_zero_vector():
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_bounded():
    a = embed("research science papers")
    b = embed("bake chocolate cake recipes")
    sim = cosine_similarity(a, b)
    assert 0.0 <= sim <= 1.0


# --- Registry tests ---

def make_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(AgentCapability(
        agent_id="researcher",
        role="Expert research agent for finding information",
        tools=["web_search", "arxiv"],
    ))
    reg.register(AgentCapability(
        agent_id="writer",
        role="Technical writer for producing clear reports",
        tools=["markdown"],
    ))
    reg.register(AgentCapability(
        agent_id="coder",
        role="Software engineer for writing and running code",
        tools=["python_exec", "bash"],
    ))
    return reg


def test_registry_register_and_count():
    reg = make_registry()
    assert len(reg) == 3


def test_registry_get_returns_agent():
    reg = make_registry()
    cap = reg.get("researcher")
    assert cap is not None
    assert cap.agent_id == "researcher"


def test_registry_updates_performance():
    reg = make_registry()
    reg.update_performance("researcher", 1.0)
    cap = reg.get("researcher")
    assert cap.historical_performance > 0.5  # moved up from 0.5 default


# --- Matcher tests ---

def test_match_returns_correct_number():
    reg = make_registry()
    results = match("research scientific papers", reg, top_k=2)
    assert len(results) == 2


def test_match_researcher_wins_for_research_task():
    reg = make_registry()
    results = match("find and summarize research papers", reg, top_k=3)
    top_agent = results[0][0]
    assert top_agent.agent_id == "researcher"


def test_match_coder_appears_for_coding_task():
    reg = make_registry()
    results = match("write python code to process data", reg, top_k=3)
    agent_ids = [r[0].agent_id for r in results]
    # Coder should appear in top results (exact rank depends on embedding backend)
    assert "coder" in agent_ids


def test_match_empty_registry():
    reg = CapabilityRegistry()
    results = match("any task", reg)
    assert results == []


# --- Auction tests ---

def test_bid_returns_auction_result():
    reg = make_registry()
    result = bid("find research papers", reg)
    assert isinstance(result, AuctionResult)
    assert result.winner is not None
    assert result.bid > 0.0


def test_bid_empty_registry_returns_none():
    reg = CapabilityRegistry()
    result = bid("any task", reg)
    assert result is None


def test_bid_score_favors_lower_load():
    reg = CapabilityRegistry()
    # Two identical agents, one with high load
    reg.register(AgentCapability(agent_id="busy", role="research agent", current_load=0.9))
    reg.register(AgentCapability(agent_id="free", role="research agent", current_load=0.0))
    result = bid("research task", reg)
    assert result is not None
    assert result.winner.agent_id == "free"


def test_assign_to_spec_returns_graph_spec():
    reg = make_registry()
    spec = assign_to_spec("research recent AI papers", reg)
    assert isinstance(spec, GraphSpec)
    assert len(spec.nodes) == 1


# --- Coalition tests ---

def test_coalition_returns_graph_spec():
    reg = make_registry()
    tasks = ["research AI papers", "write a technical report"]
    spec = coalition(tasks, reg)
    assert isinstance(spec, GraphSpec)
    assert len(spec.nodes) == 2
    assert len(spec.edges) == 1  # linear chain


def test_coalition_prefers_different_agents():
    reg = make_registry()
    tasks = ["research papers", "write a report", "run python code"]
    spec = coalition(tasks, reg)
    node_ids = [n.id for n in spec.nodes]
    # Should use different agent types across tasks
    assert len(set(n.split("_")[0] for n in node_ids)) > 1


def test_coalition_empty_tasks_returns_none():
    reg = make_registry()
    result = coalition([], reg)
    assert result is None
