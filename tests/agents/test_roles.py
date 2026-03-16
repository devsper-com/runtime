"""Tests for specialized agent roles."""

from devsper.agents.roles import (
    get_role_config,
    infer_role_from_description,
    RESEARCH_AGENT,
    CODE_AGENT,
    ANALYSIS_AGENT,
    CRITIC_AGENT,
    DEFAULT_ROLE,
)


def test_get_role_config_returns_default_for_unknown():
    cfg = get_role_config(None)
    assert cfg.name == DEFAULT_ROLE
    cfg2 = get_role_config("unknown")
    assert cfg2.name == DEFAULT_ROLE


def test_get_role_config_research():
    cfg = get_role_config(RESEARCH_AGENT)
    assert cfg.name == RESEARCH_AGENT
    assert "research" in cfg.tool_categories
    assert "literature" in cfg.prompt_prefix.lower() or "research" in cfg.prompt_prefix.lower()


def test_get_role_config_code():
    cfg = get_role_config(CODE_AGENT)
    assert cfg.name == CODE_AGENT
    assert "coding" in cfg.tool_categories or "code" in str(cfg.tool_categories).lower()


def test_infer_role_research():
    role = infer_role_from_description("Summarize the research methodology of diffusion models")
    assert role == RESEARCH_AGENT


def test_infer_role_code():
    role = infer_role_from_description("Refactor the repository and add unit tests")
    assert role == CODE_AGENT


def test_infer_role_analysis():
    role = infer_role_from_description("Analyze the dataset and compute metrics")
    assert role == ANALYSIS_AGENT


def test_infer_role_critic():
    role = infer_role_from_description("Review the document and provide feedback")
    assert role == CRITIC_AGENT


def test_infer_role_default():
    role = infer_role_from_description("Do something generic")
    assert role == DEFAULT_ROLE
