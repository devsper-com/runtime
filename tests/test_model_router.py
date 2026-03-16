"""Tests for model router (cost/latency/quality selection)."""

from devsper.providers.model_router import MODEL_REGISTRY, TaskType, select_model


def test_model_registry_has_expected_models():
    """MODEL_REGISTRY contains expected models with cost, latency, quality."""
    assert "gpt-4o" in MODEL_REGISTRY
    assert "gpt-4o-mini" in MODEL_REGISTRY
    assert "claude-3.5-sonnet" in MODEL_REGISTRY
    assert "phi-3" in MODEL_REGISTRY
    for meta in MODEL_REGISTRY.values():
        assert "cost" in meta
        assert "latency" in meta
        assert "quality" in meta


def test_select_model_planning():
    """planning → high quality (e.g. claude-3.5-sonnet)."""
    assert select_model("planning") == "claude-3.5-sonnet"


def test_select_model_analysis():
    """analysis → balanced (gpt-4o)."""
    assert select_model("analysis") == "gpt-4o"


def test_select_model_summarization():
    """summarization → balanced."""
    assert select_model("summarization") == "gpt-4o"


def test_select_model_code():
    """code → balanced."""
    assert select_model("code") == "gpt-4o"


def test_select_model_fast():
    """fast → cheapest (gpt-4o-mini)."""
    assert select_model("fast") == "gpt-4o-mini"
