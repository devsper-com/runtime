"""Tests for auto model selection (config planner/worker = 'auto')."""

from hivemind.utils.models import resolve_model


def test_resolve_model_auto_planning():
    """resolve_model('auto', 'planning') returns model_router selection for planning."""
    out = resolve_model("auto", "planning")
    assert out == "claude-3.5-sonnet"


def test_resolve_model_auto_analysis():
    """resolve_model('auto', 'analysis') returns model for analysis."""
    out = resolve_model("auto", "analysis")
    assert out == "gpt-4o"


def test_resolve_model_auto_fast():
    """resolve_model('auto', 'fast') returns cheap model."""
    out = resolve_model("auto", "fast")
    assert out == "gpt-4o-mini"


def test_resolve_model_explicit_unchanged():
    """resolve_model with explicit model returns it unchanged."""
    assert resolve_model("gpt-4o", "planning") == "gpt-4o"
    assert resolve_model("github:phi-3", "analysis") == "github:phi-3"


def test_resolve_model_empty_or_mock():
    """resolve_model('mock') returns 'mock'; empty defaults to mock."""
    assert resolve_model("mock", "planning") == "mock"
    assert resolve_model("", "planning") == "mock"
