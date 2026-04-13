from __future__ import annotations
import math
import re
from collections import Counter


_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "it", "its", "this",
    "that", "these", "those", "i", "we", "you", "he", "she", "they", "what",
    "which", "who", "when", "where", "how", "all", "each", "some", "such",
    "no", "not", "only", "so", "than", "too", "very", "just", "as", "also",
})


def compress(text: str, target_ratio: float = 0.6) -> str:
    """
    Compress text by keeping the highest TF-IDF scoring sentences.
    target_ratio: fraction of sentences to keep (0.5 = keep half).
    For ratio < 0.5, attempts LLMLingua if installed, falls back to TF-IDF.
    """
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return text

    if target_ratio < 0.5:
        try:
            return _compress_llmlingua(text, target_ratio)
        except ImportError:
            pass  # fall through to TF-IDF

    scores = _tfidf_scores(sentences)
    n_keep = max(1, round(len(sentences) * target_ratio))
    # Keep top-scored sentences, preserving original order
    ranked = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)
    keep_indices = sorted(ranked[:n_keep])
    return " ".join(sentences[i] for i in keep_indices)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT tokenizer heuristic)."""
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\b\w+\b", text) if w.lower() not in _STOPWORDS]


def _tfidf_scores(sentences: list[str]) -> list[float]:
    tokenized = [_tokenize(s) for s in sentences]
    n = len(sentences)
    all_terms = {t for tokens in tokenized for t in tokens}
    # IDF: log(N / (1 + df))
    idf = {
        term: math.log(n / (1 + sum(1 for tokens in tokenized if term in tokens)))
        for term in all_terms
    }
    scores = []
    for sent_tokens in tokenized:
        tf = Counter(sent_tokens)
        score = sum(tf[t] * idf.get(t, 0.0) for t in tf)
        scores.append(score)
    return scores


def _compress_llmlingua(text: str, ratio: float) -> str:
    from llmlingua import PromptCompressor  # type: ignore[import]
    compressor = PromptCompressor()
    result = compressor.compress_prompt(text, rate=ratio)
    return result["compressed_prompt"]
