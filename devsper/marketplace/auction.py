"""
TaskAuction: bid-based agent assignment.

Bid score = similarity × historical_performance × (1 / (1 + current_load))

The auction selects winners per task. For multi-task workflows, coalition
formation prefers complementary capability sets (low pairwise similarity).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from devsper.marketplace.registry import CapabilityRegistry, AgentCapability
from devsper.marketplace.matcher import match
from devsper.compiler.ir import GraphSpec, NodeSpec, EdgeSpec


@dataclass
class BidResult:
    agent: AgentCapability
    similarity: float
    bid_score: float


@dataclass
class AuctionResult:
    task_description: str
    winner: AgentCapability
    bid: float
    all_bids: list[BidResult] = field(default_factory=list)


def bid(
    task_description: str,
    registry: CapabilityRegistry,
    top_k: int = 5,
) -> AuctionResult | None:
    """
    Run a single-task auction. Returns the winner's BidResult, or None if no agents.
    """
    candidates = match(task_description, registry, top_k=top_k)
    if not candidates:
        return None

    bids: list[BidResult] = []
    for cap, similarity in candidates:
        load_factor = 1.0 / (1.0 + cap.current_load)
        score = similarity * cap.historical_performance * load_factor
        bids.append(BidResult(agent=cap, similarity=similarity, bid_score=score))

    bids.sort(key=lambda b: b.bid_score, reverse=True)
    winner = bids[0]
    return AuctionResult(
        task_description=task_description,
        winner=winner.agent,
        bid=winner.bid_score,
        all_bids=bids,
    )


def assign_to_spec(
    task_description: str,
    registry: CapabilityRegistry,
    top_k: int = 5,
) -> GraphSpec | None:
    """
    Run an auction and produce a single-node GraphSpec from the winner.
    Returns None if no agents registered.
    """
    result = bid(task_description, registry, top_k=top_k)
    if result is None:
        return None
    winner = result.winner
    node = NodeSpec(
        id=winner.agent_id,
        role=winner.role,
        tools=winner.tools,
        model_hint="mid",
    )
    return GraphSpec(nodes=[node], edges=[])


def coalition(
    tasks: list[str],
    registry: CapabilityRegistry,
    top_k: int = 5,
) -> GraphSpec | None:
    """
    Multi-task coalition formation.
    Assigns one agent per task, preferring complementary capabilities.
    Returns a linear GraphSpec across the coalition.
    """
    if not tasks:
        return None

    nodes: list[NodeSpec] = []
    used_agent_ids: set[str] = set()

    for i, task_desc in enumerate(tasks):
        candidates = match(task_desc, registry, top_k=top_k)
        if not candidates:
            # Fall back to a generic node
            nodes.append(NodeSpec(id=f"node_{i}", role=task_desc))
            continue

        # Pick best available agent not already in coalition
        winner_cap = None
        winner_sim = 0.0
        for cap, sim in candidates:
            if cap.agent_id not in used_agent_ids:
                winner_cap = cap
                winner_sim = sim
                break
        if winner_cap is None:
            winner_cap, winner_sim = candidates[0]  # allow reuse if no alternatives

        used_agent_ids.add(winner_cap.agent_id)
        nodes.append(NodeSpec(
            id=f"{winner_cap.agent_id}_{i}",
            role=winner_cap.role,
            tools=winner_cap.tools,
            model_hint="mid",
        ))

    edges = [EdgeSpec(src=nodes[i].id, dst=nodes[i + 1].id) for i in range(len(nodes) - 1)]
    return GraphSpec(nodes=nodes, edges=edges)
