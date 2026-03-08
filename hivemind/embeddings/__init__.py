"""Local embedding service with sentence-transformers; fallback to provider embeddings."""

from hivemind.embeddings.service import embed

__all__ = ["embed"]
