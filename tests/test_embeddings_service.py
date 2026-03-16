"""Tests for local embedding service (fallback when sentence-transformers not installed)."""

import pytest
from devsper.embeddings.service import embed, _fallback_embed


def test_embed_returns_list():
    """embed() returns a list of floats."""
    out = embed("hello world")
    assert isinstance(out, list)
    assert len(out) > 0
    assert all(isinstance(x, float) for x in out)


def test_embed_empty_fallback():
    """Empty string uses fallback and returns vector."""
    out = embed("")
    assert isinstance(out, list)
    assert len(out) > 0


def test_fallback_embed():
    """Fallback returns list of floats."""
    out = _fallback_embed("test")
    assert isinstance(out, list)
    assert len(out) > 0
