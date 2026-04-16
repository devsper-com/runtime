"""
Capability vector embedding for agents.
Uses sentence-transformers if installed (gated behind `embeddings` extra).
Falls back to TF-IDF style sparse vectors (stdlib only).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache


def embed(text: str) -> list[float]:
    """
    Embed text into a capability vector.
    Tries sentence-transformers first; falls back to TF-IDF bag-of-words.
    """
    try:
        return _embed_sentence_transformers(text)
    except ImportError:
        return _embed_tfidf(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return min(1.0, dot / (mag_a * mag_b))


# --- Vocabulary for TF-IDF fallback ---
# Built lazily from all embedded texts in the session.
_vocab: dict[str, int] = {}
_vocab_lock_counter = 0


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _embed_tfidf(text: str) -> list[float]:
    """Sparse TF-IDF vector as a dense list (zeros for unseen vocab terms)."""
    global _vocab, _vocab_lock_counter
    tokens = _tokenize(text)
    # Extend vocabulary
    for tok in tokens:
        if tok not in _vocab:
            _vocab[tok] = len(_vocab)
    if not _vocab:
        return [0.0]
    tf = Counter(tokens)
    vec = [0.0] * len(_vocab)
    for tok, count in tf.items():
        idx = _vocab.get(tok)
        if idx is not None and idx < len(vec):
            vec[idx] = count / max(1, len(tokens))
    return vec


def _embed_sentence_transformers(text: str) -> list[float]:
    from sentence_transformers import SentenceTransformer  # type: ignore[import]
    model = _get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer  # type: ignore[import]
    return SentenceTransformer("all-MiniLM-L6-v2")
