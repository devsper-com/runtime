"""
Specialized agent roles: research, code, analysis, critic.

Role determines tool access, prompt template, and model selection.
Planner assigns roles based on task type.
"""

from dataclasses import dataclass

RESEARCH_AGENT = "research_agent"
CODE_AGENT = "code_agent"
ANALYSIS_AGENT = "analysis_agent"
CRITIC_AGENT = "critic_agent"

# Dev / autonomous builder roles
ARCHITECT_AGENT = "architect_agent"
BACKEND_AGENT = "backend_agent"
FRONTEND_AGENT = "frontend_agent"
TEST_AGENT = "test_agent"
REVIEW_AGENT = "review_agent"

DEFAULT_ROLE = "general"


@dataclass
class RoleConfig:
    """Configuration for an agent role."""

    name: str
    tool_categories: list[str]  # e.g. ["research", "documents"]
    prompt_prefix: str
    model_hint: str  # e.g. "analysis", "planning" for model router


ROLE_CONFIGS: dict[str, RoleConfig] = {
    RESEARCH_AGENT: RoleConfig(
        name=RESEARCH_AGENT,
        tool_categories=[
            "research",
            "research_advanced",
            "documents",
            "knowledge",
            "memory",
            "mcp",
        ],
        prompt_prefix="You are a research specialist. Focus on literature, citations, methodology, and evidence.",
        model_hint="analysis",
    ),
    CODE_AGENT: RoleConfig(
        name=CODE_AGENT,
        tool_categories=["coding", "code_intelligence", "filesystem", "system", "mcp"],
        prompt_prefix="You are a code specialist. Focus on implementation, structure, tests, and refactoring.",
        model_hint="analysis",
    ),
    ANALYSIS_AGENT: RoleConfig(
        name=ANALYSIS_AGENT,
        tool_categories=["data", "data_science", "math", "experiments", "knowledge", "mcp"],
        prompt_prefix="You are an analysis specialist. Focus on data, metrics, statistics, and interpretation.",
        model_hint="analysis",
    ),
    CRITIC_AGENT: RoleConfig(
        name=CRITIC_AGENT,
        tool_categories=["documents", "memory", "knowledge"],
        prompt_prefix="You are a critic/reviewer. Evaluate quality, consistency, and gaps. Be concise and constructive.",
        model_hint="analysis",
    ),
    DEFAULT_ROLE: RoleConfig(
        name=DEFAULT_ROLE,
        tool_categories=[],  # empty = no filter; all tools (including mcp) eligible
        prompt_prefix="You are an AI worker in a distributed system.",
        model_hint="analysis",
    ),
    # Dev / autonomous builder roles
    ARCHITECT_AGENT: RoleConfig(
        name=ARCHITECT_AGENT,
        tool_categories=["code_intelligence", "filesystem"],
        prompt_prefix="You are an architect. Design system structure, APIs, and component layout. Output clear architecture plans (backend/frontend stack, modules, data flow).",
        model_hint="planning",
    ),
    BACKEND_AGENT: RoleConfig(
        name=BACKEND_AGENT,
        tool_categories=["coding", "code_intelligence", "filesystem", "system"],
        prompt_prefix="You are a backend specialist. Implement APIs, models, and server logic. Prefer FastAPI/Flask patterns and clear interfaces.",
        model_hint="analysis",
    ),
    FRONTEND_AGENT: RoleConfig(
        name=FRONTEND_AGENT,
        tool_categories=["coding", "filesystem", "system"],
        prompt_prefix="You are a frontend specialist. Implement UI components, pages, and client logic. Prefer simple HTML/JS or React patterns.",
        model_hint="analysis",
    ),
    TEST_AGENT: RoleConfig(
        name=TEST_AGENT,
        tool_categories=["coding", "code_intelligence", "filesystem", "system"],
        prompt_prefix="You are a test specialist. Write unit and integration tests. Use pytest for Python; ensure coverage of main flows.",
        model_hint="analysis",
    ),
    REVIEW_AGENT: RoleConfig(
        name=REVIEW_AGENT,
        tool_categories=["code_intelligence", "coding", "filesystem"],
        prompt_prefix="You are a code reviewer. Check correctness, style, and gaps. Suggest concrete fixes. Be concise.",
        model_hint="analysis",
    ),
}


def get_role_config(role: str | None) -> RoleConfig:
    """Return config for the given role, or default if unknown/None.

    If an optimized prompt exists at .devsper/optimized_prompts/{role}.json
    (written by EvalRunner after prompt optimization), it is used in place of
    the hardcoded prompt_prefix.
    """
    base = ROLE_CONFIGS.get(role or DEFAULT_ROLE, ROLE_CONFIGS[DEFAULT_ROLE]) if role else ROLE_CONFIGS[DEFAULT_ROLE]
    optimized = _load_optimized_prompt(base.name)
    if optimized:
        from dataclasses import replace
        return replace(base, prompt_prefix=optimized)
    return base


def _load_optimized_prompt(role: str) -> str | None:
    """Load persisted optimized prompt for a role, if it exists."""
    import json
    from pathlib import Path

    p = Path(".devsper/optimized_prompts") / f"{role}.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        prompt = data.get("prompt_prefix", "")
        return prompt if prompt else None
    except Exception:
        return None


# Keywords to infer role from task description
RESEARCH_KEYWORDS = [
    "research",
    "paper",
    "literature",
    "cite",
    "survey",
    "methodology",
    "findings",
]
CODE_KEYWORDS = [
    "code",
    "implement",
    "refactor",
    "test",
    "repository",
    "function",
    "api",
    "lint",
    "list",
    "directory",
    "files",
    "contents",
    "path",
    "read file",
    "write file",
]
ANALYSIS_KEYWORDS = [
    "analyze",
    "data",
    "metric",
    "statistic",
    "plot",
    "dataset",
    "experiment",
    "evaluate",
]
CRITIC_KEYWORDS = [
    "review",
    "critique",
    "evaluate",
    "quality",
    "check",
    "verify",
    "feedback",
]

# Dev builder: explicit roles are set by planner; no inference needed for build tasks
DEV_ROLES = [
    ARCHITECT_AGENT,
    BACKEND_AGENT,
    FRONTEND_AGENT,
    TEST_AGENT,
    REVIEW_AGENT,
]


def infer_role_from_description(description: str) -> str:
    """Infer agent role from task description. Returns role name or DEFAULT_ROLE."""
    text = (description or "").lower()
    scores = {
        RESEARCH_AGENT: sum(1 for k in RESEARCH_KEYWORDS if k in text),
        CODE_AGENT: sum(1 for k in CODE_KEYWORDS if k in text),
        ANALYSIS_AGENT: sum(1 for k in ANALYSIS_KEYWORDS if k in text),
        CRITIC_AGENT: sum(1 for k in CRITIC_KEYWORDS if k in text),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else DEFAULT_ROLE
