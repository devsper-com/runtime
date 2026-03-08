"""
Automatic model routing by cost, latency, and quality tier.

Use select_model(task_type) to get the best model for a given task type.
"""

from typing import Literal

TaskType = Literal["planning", "analysis", "summarization", "code", "fast"]

# cost: relative cost per request, latency: relative latency tier, quality: 1-5
MODEL_REGISTRY: dict[str, dict[str, float]] = {
    "gpt-4o": {"cost": 0.01, "latency": 2, "quality": 5},
    "gpt-4o-mini": {"cost": 0.002, "latency": 1, "quality": 3},
    "claude-3.5-sonnet": {"cost": 0.008, "latency": 2, "quality": 5},
    "phi-3": {"cost": 0.001, "latency": 1, "quality": 2},
}


def select_model(task_type: TaskType) -> str:
    """
    Select the best model for the given task type.

    - planning → high quality (claude-3.5-sonnet)
    - analysis → balanced (gpt-4o)
    - summarization → balanced (gpt-4o)
    - code → balanced (gpt-4o)
    - fast → cheapest / low latency (gpt-4o-mini)
    """
    if task_type == "planning":
        return "claude-3.5-sonnet"
    if task_type == "analysis":
        return "gpt-4o"
    if task_type == "summarization":
        return "gpt-4o"
    if task_type == "code":
        return "gpt-4o"
    if task_type == "fast":
        return "gpt-4o-mini"
    return "gpt-4o-mini"
