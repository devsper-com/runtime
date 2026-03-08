"""
Local embedding service using sentence-transformers (all-MiniLM-L6-v2).
Falls back to provider embeddings (memory.embeddings.embed_text) if local model unavailable.
"""


def embed(text: str) -> list[float]:
    """
    Return embedding vector for text. Tries local sentence-transformers model first,
    then falls back to provider embeddings (OpenAI/stub).
    """
    if not text or not str(text).strip():
        return _fallback_embed(" ")
    vec = _local_embed(text)
    if vec is not None:
        return vec
    return _fallback_embed(text)


def _local_embed(text: str) -> list[float] | None:
    """Use sentence-transformers all-MiniLM-L6-v2 if available."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        emb = model.encode(text[:8192], convert_to_numpy=True)
        return emb.tolist()
    except Exception:
        return None


def _fallback_embed(text: str) -> list[float]:
    """Use provider embeddings (OpenAI or stub) from memory.embeddings."""
    from hivemind.memory.embeddings import embed_text

    return embed_text(text)
