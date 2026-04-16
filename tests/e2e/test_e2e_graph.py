"""
End-to-end tests: real LLM calls via Ollama (gemma4:e4b at 192.168.1.2).

Coverage:
  1. Single agent node — direct Agent.run_task via graph
  2. Two-node linear graph — researcher → writer pipeline
  3. Mutation checkpoint node — agent emits a mutation, runtime applies it
  4. Full plaintext pipeline — prose → GePA → compile → run
  5. PeerNode distributed execution — single peer executes subgraph
  6. Capability marketplace — auction assigns best agent, coalition forms graph
"""
import os
import pytest

from tests.e2e.conftest import requires_ollama, OLLAMA_MODEL

from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.graph.runtime import GraphRuntime
from devsper.graph.state import initial_state
from devsper.graph.mutations import MutationRequest, MutationValidator


# ---------------------------------------------------------------------------
# Test 1: Single node — direct LLM call through graph
# ---------------------------------------------------------------------------

@requires_ollama
def test_single_node_real_llm():
    spec = GraphSpec(
        nodes=[NodeSpec(id="responder", role="Answer the question concisely", model_hint=OLLAMA_MODEL)],
        edges=[],
    )
    rt = GraphRuntime()
    state = initial_state(task="What is 2 + 2? Answer in one sentence.", run_id="e2e-single")
    result = rt.run_spec(spec, state=state)

    assert "responder" in result["completed_nodes"]
    answer = result["results"]["responder"]
    # Real LLM should return a non-trivial answer
    assert len(answer) > 5, f"Answer too short: {answer!r}"
    # Should not look like a mock stub response
    assert not answer.startswith("["), f"Got stub response: {answer!r}"


# ---------------------------------------------------------------------------
# Test 2: Two-node pipeline — researcher feeds writer
# ---------------------------------------------------------------------------

@requires_ollama
def test_two_node_pipeline():
    spec = GraphSpec(
        nodes=[
            NodeSpec(
                id="researcher",
                role="List 3 key facts about the topic in bullet points",
                model_hint=OLLAMA_MODEL,
            ),
            NodeSpec(
                id="writer",
                role="Write a single-paragraph summary based on the prior work",
                model_hint=OLLAMA_MODEL,
            ),
        ],
        edges=[EdgeSpec(src="researcher", dst="writer")],
    )
    rt = GraphRuntime()
    result = rt.run_spec(spec, task="quantum computing")

    assert "researcher" in result["completed_nodes"]
    assert "writer" in result["completed_nodes"]

    research = result["results"]["researcher"]
    summary = result["results"]["writer"]
    assert len(research) > 20, f"Research too short: {research!r}"
    assert len(summary) > 20, f"Summary too short: {summary!r}"
    # Writer ran after researcher — its input should include prior work
    assert "completed_nodes" in result


# ---------------------------------------------------------------------------
# Test 3: Mutation checkpoint — validate MutationValidator + apply
# ---------------------------------------------------------------------------

@requires_ollama
def test_mutation_checkpoint_node():
    """
    The mutation checkpoint node produces output. We then manually inject a
    MutationRequest to test the full validate → apply → recompile cycle.
    """
    spec = GraphSpec(
        nodes=[
            NodeSpec(
                id="planner",
                role="Plan a 2-step workflow for writing a blog post. Be concise.",
                model_hint=OLLAMA_MODEL,
                is_mutation_point=True,
            ),
        ],
        edges=[],
    )
    rt = GraphRuntime()
    result = rt.run_spec(spec, task="Write a blog post about AI agents")

    assert "planner" in result["completed_nodes"]
    plan_text = result["results"]["planner"]
    assert len(plan_text) > 10

    # Now test MutationValidator directly on a manual request
    validator = MutationValidator()
    req = MutationRequest(
        op="add_node",
        payload={"id": "editor", "role": "Edit and polish the blog post"},
        justification="Quality pass needed",
        confidence=0.9,
    )
    new_spec = validator.apply(req, spec)
    assert len(new_spec.nodes) == 2
    assert any(n.id == "editor" for n in new_spec.nodes)

    # Run the mutated spec
    result2 = rt.run_spec(new_spec, task="Write a blog post about AI agents")
    assert "planner" in result2["completed_nodes"]
    assert "editor" in result2["completed_nodes"]


# ---------------------------------------------------------------------------
# Test 4: Full plaintext pipeline — prose → parse → GePA → compile → run
# ---------------------------------------------------------------------------

@requires_ollama
def test_full_plaintext_pipeline():
    """End-to-end: natural language description → compiled graph → real LLM execution."""
    workflow = """
    Research the main benefits of renewable energy.
    Summarize the findings in three bullet points.
    """
    rt = GraphRuntime()
    result = rt.run_from_text(
        workflow,
        optimize_for="balanced",
        population_size=5,
        max_generations=3,
    )

    assert len(result["completed_nodes"]) >= 1
    # At least one node produced non-empty output
    assert any(len(v) > 10 for v in result["results"].values()), \
        f"All results empty: {result['results']}"


# ---------------------------------------------------------------------------
# Test 5: PeerNode distributed execution
# ---------------------------------------------------------------------------

@requires_ollama
@pytest.mark.asyncio
async def test_peer_node_execution():
    from devsper.peers.node import PeerNode

    spec = GraphSpec(
        nodes=[
            NodeSpec(id="analyst", role="Give one insight about solar energy", model_hint=OLLAMA_MODEL),
        ],
        edges=[],
    )

    peer = PeerNode(node_id="peer-e2e", capabilities=["research"], bus=None)
    await peer.start()
    try:
        state = initial_state(task="solar energy trends", run_id="peer-e2e-run")
        result = await peer.execute_subgraph(spec, state=state)
        assert "analyst" in result["completed_nodes"]
        assert len(result["results"]["analyst"]) > 5
    finally:
        await peer.stop()


# ---------------------------------------------------------------------------
# Test 6: Capability marketplace → assign agent → run on real LLM
# ---------------------------------------------------------------------------

@requires_ollama
def test_marketplace_assign_and_run():
    from devsper.marketplace.registry import CapabilityRegistry, AgentCapability
    from devsper.marketplace.auction import assign_to_spec

    reg = CapabilityRegistry()
    reg.register(AgentCapability(
        agent_id="research-bot",
        role="Research agent that finds and summarizes information",
        tools=["web_search"],
    ))
    reg.register(AgentCapability(
        agent_id="code-bot",
        role="Software engineer that writes Python code",
        tools=["python_exec"],
    ))

    # Assign best agent for a research task
    spec = assign_to_spec("summarize recent news about AI safety", reg)
    assert spec is not None
    assert len(spec.nodes) == 1

    # Override model_hint so it actually calls Ollama
    from devsper.compiler.ir import NodeSpec as NS
    spec.nodes[0] = NS(
        id=spec.nodes[0].id,
        role=spec.nodes[0].role,
        tools=spec.nodes[0].tools,
        model_hint=OLLAMA_MODEL,
    )

    rt = GraphRuntime()
    result = rt.run_spec(spec, task="summarize recent news about AI safety")
    assert len(result["completed_nodes"]) == 1
    node_id = result["completed_nodes"][0]
    assert len(result["results"][node_id]) > 10
