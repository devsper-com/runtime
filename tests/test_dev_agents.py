"""Tests for dev agent roles (architect, backend, frontend, test, review)."""

from devsper.agents.roles import (
    get_role_config,
    ARCHITECT_AGENT,
    BACKEND_AGENT,
    FRONTEND_AGENT,
    TEST_AGENT,
    REVIEW_AGENT,
    DEV_ROLES,
)


def test_dev_roles_defined():
    assert ARCHITECT_AGENT == "architect_agent"
    assert BACKEND_AGENT == "backend_agent"
    assert FRONTEND_AGENT == "frontend_agent"
    assert TEST_AGENT == "test_agent"
    assert REVIEW_AGENT == "review_agent"
    assert len(DEV_ROLES) == 5


def test_get_role_config_architect():
    cfg = get_role_config(ARCHITECT_AGENT)
    assert cfg.name == ARCHITECT_AGENT
    assert "architect" in cfg.prompt_prefix.lower()
    assert "code_intelligence" in cfg.tool_categories or "filesystem" in cfg.tool_categories


def test_get_role_config_backend():
    cfg = get_role_config(BACKEND_AGENT)
    assert cfg.name == BACKEND_AGENT
    assert "backend" in cfg.prompt_prefix.lower() or "api" in cfg.prompt_prefix.lower()
    assert "coding" in cfg.tool_categories


def test_get_role_config_frontend():
    cfg = get_role_config(FRONTEND_AGENT)
    assert cfg.name == FRONTEND_AGENT
    assert "frontend" in cfg.prompt_prefix.lower() or "ui" in cfg.prompt_prefix.lower()


def test_get_role_config_test():
    cfg = get_role_config(TEST_AGENT)
    assert cfg.name == TEST_AGENT
    assert "test" in cfg.prompt_prefix.lower()
    assert "coding" in cfg.tool_categories


def test_get_role_config_review():
    cfg = get_role_config(REVIEW_AGENT)
    assert cfg.name == REVIEW_AGENT
    assert "review" in cfg.prompt_prefix.lower() or "critic" in cfg.prompt_prefix.lower()
