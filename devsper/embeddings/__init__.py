"""Local embedding service with sentence-transformers; fallback to provider embeddings."""

from devsper.embeddings.service import embed

__all__ = ["embed"]
