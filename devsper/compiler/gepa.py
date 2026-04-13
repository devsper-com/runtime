from __future__ import annotations
import copy
import random
from dataclasses import dataclass, field
from .ir import GraphSpec, NodeSpec, EdgeSpec
from .objectives import score_f1_token_cost, score_f2_task_fidelity, score_f3_predicted_performance


@dataclass
class GEPAConfig:
    population_size: int = 50
    max_generations: int = 100
    convergence_patience: int = 10
    crossover_rate: float = 0.7
    mutation_rate: float = 0.3
    optimize_for: str = "balanced"  # "cost" | "quality" | "speed" | "balanced"
    historical_scores: dict[str, float] = field(default_factory=dict)
    seed: int = 42


@dataclass
class _Individual:
    spec: GraphSpec
    scores: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rank: int = 0
    crowding_distance: float = 0.0


def optimize(
    initial_spec: GraphSpec,
    original_prompt: str,
    config: GEPAConfig | None = None,
) -> list[GraphSpec]:
    """
    Run Genetic-Pareto optimization over GraphSpec population.
    Returns Pareto front sorted by config.optimize_for priority.
    """
    if config is None:
        config = GEPAConfig()
    rng = random.Random(config.seed)

    population = _init_population(initial_spec, config.population_size, rng)
    _evaluate(population, original_prompt, config.historical_scores)

    prev_front_size = -1
    patience = 0

    for _ in range(config.max_generations):
        offspring = _breed(population, config, rng)
        _evaluate(offspring, original_prompt, config.historical_scores)
        combined = population + offspring
        population = _select(combined, config.population_size)

        front_size = sum(1 for ind in population if ind.rank == 0)
        if front_size == prev_front_size:
            patience += 1
            if patience >= config.convergence_patience:
                break
        else:
            patience = 0
        prev_front_size = front_size

    pareto_front = [ind.spec for ind in population if ind.rank == 0]
    return _sort_by_priority(pareto_front, original_prompt, config)


def _init_population(seed: GraphSpec, size: int, rng: random.Random) -> list[_Individual]:
    pop = [_Individual(spec=copy.deepcopy(seed))]
    while len(pop) < size:
        mutant = _mutate(copy.deepcopy(seed), rng)
        pop.append(_Individual(spec=mutant))
    return pop


def _evaluate(
    population: list[_Individual],
    prompt: str,
    historical: dict[str, float],
) -> None:
    for ind in population:
        f1 = score_f1_token_cost(ind.spec)
        f2 = score_f2_task_fidelity(ind.spec, prompt)
        f3 = score_f3_predicted_performance(ind.spec, historical)
        ind.scores = (f1, f2, f3)


def _breed(
    population: list[_Individual],
    config: GEPAConfig,
    rng: random.Random,
) -> list[_Individual]:
    offspring = []
    while len(offspring) < len(population):
        pa = rng.choice(population)
        pb = rng.choice(population)
        spec = _crossover(pa.spec, pb.spec, rng) if rng.random() < config.crossover_rate else copy.deepcopy(pa.spec)
        if rng.random() < config.mutation_rate:
            spec = _mutate(spec, rng)
        offspring.append(_Individual(spec=spec))
    return offspring


def _crossover(a: GraphSpec, b: GraphSpec, rng: random.Random) -> GraphSpec:
    child = copy.deepcopy(a)
    if b.nodes:
        donor = copy.deepcopy(rng.choice(b.nodes))
        donor.id = f"{donor.id}_x{rng.randint(0, 999)}"
        existing_ids = {n.id for n in child.nodes}
        if donor.id not in existing_ids:
            child.nodes.append(donor)
            if len(child.nodes) >= 2:
                child.edges.append(EdgeSpec(src=child.nodes[-2].id, dst=donor.id))
    return child


def _mutate(spec: GraphSpec, rng: random.Random) -> GraphSpec:
    op = rng.choice(["toggle_mutation_point", "change_model_hint", "add_node", "remove_node"])
    if op == "toggle_mutation_point" and spec.nodes:
        node = rng.choice(spec.nodes)
        node.is_mutation_point = not node.is_mutation_point
    elif op == "change_model_hint" and spec.nodes:
        node = rng.choice(spec.nodes)
        node.model_hint = rng.choice(["fast", "mid", "slow"])
    elif op == "add_node":
        new_id = f"node_m{len(spec.nodes)}_{rng.randint(0, 999)}"
        spec.nodes.append(NodeSpec(id=new_id, role="Supplementary analysis agent", model_hint="fast"))
        if len(spec.nodes) >= 2:
            spec.edges.append(EdgeSpec(src=spec.nodes[-2].id, dst=new_id))
    elif op == "remove_node" and len(spec.nodes) > 1:
        idx = rng.randrange(len(spec.nodes))
        removed = spec.nodes.pop(idx)
        spec.edges = [e for e in spec.edges if e.src != removed.id and e.dst != removed.id]
    spec.mutation_points = [n.id for n in spec.nodes if n.is_mutation_point]
    return spec


def _select(combined: list[_Individual], size: int) -> list[_Individual]:
    fronts = _non_dominated_sort(combined)
    selected: list[_Individual] = []
    for front in fronts:
        if len(selected) + len(front) <= size:
            selected.extend(front)
        else:
            _assign_crowding(front)
            front.sort(key=lambda x: x.crowding_distance, reverse=True)
            selected.extend(front[: size - len(selected)])
            break
    return selected


def _non_dominated_sort(population: list[_Individual]) -> list[list[_Individual]]:
    n = len(population)
    dom_count = [0] * n
    dominated: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                if _dominates(population[i].scores, population[j].scores):
                    dominated[i].append(j)
                elif _dominates(population[j].scores, population[i].scores):
                    dom_count[i] += 1
    fronts: list[list[_Individual]] = []
    current = [i for i in range(n) if dom_count[i] == 0]
    rank = 0
    while current:
        front = [population[i] for i in current]
        for ind in front:
            ind.rank = rank
        fronts.append(front)
        nxt: list[int] = []
        for i in current:
            for j in dominated[i]:
                dom_count[j] -= 1
                if dom_count[j] == 0:
                    nxt.append(j)
        current = nxt
        rank += 1
    return fronts


def _dominates(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    """a dominates b: a ≤ b on f1 (min), a ≥ b on f2/f3 (max), strict on at least one."""
    a1, a2, a3 = a
    b1, b2, b3 = b
    at_least_as_good = (a1 <= b1) and (a2 >= b2) and (a3 >= b3)
    strictly_better = (a1 < b1) or (a2 > b2) or (a3 > b3)
    return at_least_as_good and strictly_better


def _assign_crowding(front: list[_Individual]) -> None:
    n = len(front)
    for ind in front:
        ind.crowding_distance = 0.0
    for obj_idx in range(3):
        reverse = obj_idx != 0  # f1: minimize (ascending), f2/f3: maximize (descending)
        srt = sorted(front, key=lambda x: x.scores[obj_idx], reverse=reverse)
        srt[0].crowding_distance = float("inf")
        srt[-1].crowding_distance = float("inf")
        obj_range = abs(srt[0].scores[obj_idx] - srt[-1].scores[obj_idx])
        if obj_range == 0:
            continue
        for i in range(1, n - 1):
            srt[i].crowding_distance += (
                abs(srt[i - 1].scores[obj_idx] - srt[i + 1].scores[obj_idx]) / obj_range
            )


def _sort_by_priority(front: list[GraphSpec], prompt: str, config: GEPAConfig) -> list[GraphSpec]:
    if config.optimize_for == "cost":
        return sorted(front, key=score_f1_token_cost)
    if config.optimize_for == "quality":
        return sorted(front, key=lambda s: score_f2_task_fidelity(s, prompt), reverse=True)
    if config.optimize_for == "speed":
        return sorted(front, key=lambda s: sum(1 for n in s.nodes if n.model_hint == "fast"), reverse=True)
    # balanced: closest to utopia (f1=0, f2=1, f3=1)
    def utopia_dist(spec: GraphSpec) -> float:
        f1 = score_f1_token_cost(spec)
        f2 = score_f2_task_fidelity(spec, prompt)
        f3 = score_f3_predicted_performance(spec, config.historical_scores)
        return f1 ** 2 + (1 - f2) ** 2 + (1 - f3) ** 2
    return sorted(front, key=utopia_dist)
