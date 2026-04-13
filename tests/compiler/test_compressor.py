import pytest
from devsper.compiler.compressor import compress, estimate_tokens


LONG_TEXT = (
    "Research is the systematic process of investigating a topic in depth. "
    "It involves gathering information from multiple authoritative sources. "
    "The researcher then synthesizes this information into coherent findings. "
    "Finally, the findings are presented in a clear and concise written report. "
    "The report should be accessible to the target technical audience. "
    "It must also be accurate, well-structured, and properly referenced throughout."
)


def test_compress_reduces_token_count():
    original_tokens = estimate_tokens(LONG_TEXT)
    compressed = compress(LONG_TEXT, target_ratio=0.5)
    compressed_tokens = estimate_tokens(compressed)
    assert compressed_tokens < original_tokens


def test_compress_single_sentence_returned_unchanged():
    single = "Research quantum computing fundamentals."
    result = compress(single, target_ratio=0.5)
    assert result == single


def test_compress_preserves_key_content_words():
    compressed = compress(LONG_TEXT, target_ratio=0.6)
    # At least some high-signal words must survive
    key_words = ["research", "findings", "report", "information", "synthesizes"]
    assert any(w in compressed.lower() for w in key_words)


def test_compress_ratio_1_returns_all_sentences():
    result = compress(LONG_TEXT, target_ratio=1.0)
    # All sentences kept — result should contain all content
    assert len(result) >= len(LONG_TEXT) * 0.8


def test_estimate_tokens_min_one():
    assert estimate_tokens("a") == 1


def test_estimate_tokens_scales_with_length():
    short = estimate_tokens("hello world")
    long = estimate_tokens("hello world " * 100)
    assert long > short
