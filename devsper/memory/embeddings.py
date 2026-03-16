"""
Lightweight embeddings for memory index.

Uses optional OpenAI embeddings when OPENAI_API_KEY is set;
otherwise a deterministic stub for tests and offline use.
"""

import hashlib
import os
import re

DEFAULT_DIM = 64


def _stub_embed(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """Deterministic pseudo-embedding from text (no API). Normalized to unit-ish scale."""
    words = re.findall(r"\w+", text.lower())
    if not words:
        return [0.0] * dim
    vec = [0.0] * dim
    for w in words:
        h = hashlib.sha256(w.encode()).hexdigest()
        for i in range(0, min(dim * 2, len(h)), 2):
            vec[i % dim] += int(h[i : i + 2], 16) / 255.0
    total = sum(x * x for x in vec) ** 0.5
    if total > 0:
        vec = [x / total for x in vec]
    return vec


def _openai_embed(text: str, dim: int = DEFAULT_DIM) -> list[float] | None:
    """Use OpenAI embeddings if available. Returns None if not configured."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not text.strip():
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        r = client.embeddings.create(
            input=text[:8192],
            model="text-embedding-3-small",
        )
        emb = r.data[0].embedding
        if dim and len(emb) > dim:
            return emb[:dim]
        return emb
    except Exception:
        return None


def embed_text(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """
    Return an embedding vector for text.
    Uses OpenAI when OPENAI_API_KEY is set; otherwise a deterministic stub.
    """
    if not text or not text.strip():
        return _stub_embed(" ", dim)
    out = _openai_embed(text, dim)
    return out if out is not None else _stub_embed(text, dim)
