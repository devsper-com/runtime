from __future__ import annotations
import math
import re
from collections import Counter
from .ir import GraphSpec
from .compressor import estimate_tokens


def score_f1_token_cost(spec: GraphSpec) -> float:
    """
    f1: token cost. Lower = cheaper. Returns 0.0–1.0.
    Normalized assuming 500 tokens per node is maximally expensive (1.0).
    """
    total = sum(
        estimate_tokens(node.role + " " + " ".join(node.tools))
        for node in spec.nodes
    )
    return min(1.0, total / (500 * max(1, len(spec.nodes))))


def score_f2_task_fidelity(spec: GraphSpec, original_prompt: str) -> float:
    """
    f2: task fidelity. Higher = spec better preserves original intent. Returns 0.0–1.0.
    Cosine similarity between TF-IDF vectors of spec text and original prompt.
    """
    spec_text = " ".join(node.role + " " + " ".join(node.tools) for node in spec.nodes)
    return _cosine_similarity(spec_text, original_prompt)


def score_f3_predicted_performance(
    spec: GraphSpec,
    historical_scores: dict[str, float] | None = None,
) -> float:
    """
    f3: predicted agent performance. Higher = better. Returns 0.0–1.0.
    Mean of historical role-level performance scores. Defaults to 0.5 for unknown roles.
    """
    if not historical_scores:
        return 0.5
    per_node = [historical_scores.get(node.role, 0.5) for node in spec.nodes]
    return sum(per_node) / len(per_node)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _cosine_similarity(a: str, b: str) -> float:
    ta = Counter(_tokenize(a))
    tb = Counter(_tokenize(b))
    terms = set(ta) | set(tb)
    if not terms:
        return 0.0
    dot = sum(ta.get(t, 0) * tb.get(t, 0) for t in terms)
    mag_a = math.sqrt(sum(v ** 2 for v in ta.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in tb.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return min(1.0, dot / (mag_a * mag_b))
