"""
Smart tool selection: filter by category and select top_k tools by semantic similarity to the task.
"""

import os

from hivemind.memory.embeddings import embed_text
from hivemind.tools.base import Tool
from hivemind.tools.registry import list_tools


def _tool_category(tool: Tool) -> str:
    """Infer category from tool.category or from module path (e.g. hivemind.tools.research -> research)."""
    if getattr(tool, "category", "") and str(tool.category).strip():
        return str(tool.category).strip().lower()
    module = getattr(tool.__class__, "__module__", "") or ""
    if "hivemind.tools." in module:
        parts = module.split(".")
        for i, p in enumerate(parts):
            if p == "tools" and i + 1 < len(parts):
                return parts[i + 1].lower()
    return "general"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _top_k_by_similarity(
    task_description: str,
    tools: list[Tool],
    top_k: int,
) -> list[Tool]:
    """Return top_k tools from the list by semantic similarity to task_description."""
    if not tools or top_k <= 0:
        return tools
    task_embedding = embed_text(task_description or " ")
    tool_texts = [f"{t.name}: {t.description}" for t in tools]
    tool_embeddings = [embed_text(t) for t in tool_texts]
    scored = [
        (t, _cosine_similarity(task_embedding, te))
        for t, te in zip(tools, tool_embeddings)
    ]
    scored.sort(key=lambda x: -x[1])
    return [t for t, _ in scored[:top_k]]


def select_tools_for_task(
    task_description: str,
    top_k: int = 12,
    enabled_categories: list[str] | None = None,
) -> list[Tool]:
    """
    Return tools most relevant to the task: filter by enabled_categories (if set),
    then by semantic similarity, return top_k. If top_k <= 0, return all (no limit).
    """
    all_tools = list_tools()
    if enabled_categories is not None and len(enabled_categories) > 0:
        allowed = {c.lower().strip() for c in enabled_categories}
        all_tools = [t for t in all_tools if _tool_category(t) in allowed]
    if not all_tools:
        return []
    if top_k <= 0:
        return all_tools
    return _top_k_by_similarity(task_description, all_tools, top_k)


def get_tools_for_task(
    task_description: str,
    config: object | None = None,
    role: str | None = None,
    score_store: object | None = None,
) -> list[Tool]:
    """
    Return tools for the agent: use selector when config has tools.top_k > 0,
    otherwise return all tools. If role is set, filter by role's tool_categories.
    When score_store is provided and HIVEMIND_DISABLE_TOOL_SCORING is not set,
    uses blended similarity + reliability ranking.
    """
    if config is None:
        try:
            from hivemind.config import get_config
            config = get_config()
        except Exception:
            config = None

    tools_config = getattr(config, "tools", None) if config else None
    top_k = getattr(tools_config, "top_k", 0) if tools_config else 0
    enabled = getattr(tools_config, "enabled", None) if tools_config else None

    if role:
        from hivemind.agents.roles import get_role_config
        role_config = get_role_config(role)
        if role_config.tool_categories:
            enabled = role_config.tool_categories

    all_tools = list_tools()
    if enabled is not None and len(enabled) > 0:
        allowed = {c.lower().strip() for c in enabled}
        all_tools = [t for t in all_tools if _tool_category(t) in allowed]

    if not all_tools:
        return []
    if top_k <= 0:
        return all_tools

    top_k_val = top_k
    if top_k_val <= 0:
        return all_tools

    use_scoring = (
        score_store is not None
        and os.environ.get("HIVEMIND_DISABLE_TOOL_SCORING", "").strip() != "1"
    )
    if use_scoring:
        from hivemind.tools.scoring.selector import select_tools_scored
        return select_tools_scored(
            task_description or "",
            all_tools,
            top_k_val,
            score_store,
        )
    return _top_k_by_similarity(task_description or "", all_tools, top_k_val)
