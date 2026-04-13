import pytest
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec
from devsper.compiler.gepa import optimize, GEPAConfig


def make_seed() -> GraphSpec:
    return GraphSpec(
        nodes=[
            NodeSpec(id="n0", role="Research quantum computing trends thoroughly"),
            NodeSpec(id="n1", role="Synthesize findings into key thematic areas"),
            NodeSpec(id="n2", role="Write final technical report for engineers", is_mutation_point=True),
        ],
        edges=[
            EdgeSpec(src="n0", dst="n1"),
            EdgeSpec(src="n1", dst="n2"),
        ],
    )


PROMPT = "research quantum computing and write a technical report"


def test_optimize_returns_list_of_graph_specs():
    config = GEPAConfig(population_size=10, max_generations=5)
    front = optimize(make_seed(), PROMPT, config)
    assert isinstance(front, list)
    assert len(front) >= 1
    assert all(isinstance(s, GraphSpec) for s in front)


def test_optimize_front_all_have_nodes():
    config = GEPAConfig(population_size=10, max_generations=5)
    front = optimize(make_seed(), PROMPT, config)
    assert all(len(s.nodes) >= 1 for s in front)


def test_optimize_cost_priority_cheapest_first():
    config = GEPAConfig(population_size=20, max_generations=10, optimize_for="cost")
    front = optimize(make_seed(), PROMPT, config)
    from devsper.compiler.objectives import score_f1_token_cost
    costs = [score_f1_token_cost(s) for s in front]
    # First element should be cheaper or equal to last
    assert costs[0] <= costs[-1] + 0.01  # small tolerance for ties


def test_optimize_quality_priority_highest_fidelity_first():
    config = GEPAConfig(population_size=20, max_generations=10, optimize_for="quality")
    front = optimize(make_seed(), PROMPT, config)
    from devsper.compiler.objectives import score_f2_task_fidelity
    scores = [score_f2_task_fidelity(s, PROMPT) for s in front]
    assert scores[0] >= scores[-1] - 0.01


def test_optimize_convergence_terminates_early():
    """convergence_patience=2 means it stops well before max_generations=500."""
    import time
    config = GEPAConfig(
        population_size=5,
        max_generations=500,
        convergence_patience=2,
    )
    start = time.time()
    front = optimize(make_seed(), PROMPT, config)
    elapsed = time.time() - start
    assert elapsed < 15.0  # must terminate early
    assert len(front) >= 1


def test_optimize_deterministic_with_same_seed():
    config = GEPAConfig(population_size=10, max_generations=5)
    front_a = optimize(make_seed(), PROMPT, config)
    front_b = optimize(make_seed(), PROMPT, config)
    # Same number of solutions on Pareto front
    assert len(front_a) == len(front_b)
