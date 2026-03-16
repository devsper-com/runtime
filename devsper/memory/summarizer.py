"""
Memory summarization: summarize a set of memory records into shorter text.
Optional LLM or extractive (first N chars / key sentences).
"""

from devsper.memory.memory_types import MemoryRecord

MAX_EXTRACTIVE_CHARS = 4000


def summarize_extractive(records: list[MemoryRecord], max_chars: int = MAX_EXTRACTIVE_CHARS) -> str:
    """Concatenate record contents up to max_chars (no LLM)."""
    parts: list[str] = []
    total = 0
    for r in records:
        if total >= max_chars:
            break
        chunk = (r.content or "")[: max_chars - total]
        if chunk:
            parts.append(chunk)
            total += len(chunk)
    return "\n\n".join(parts) if parts else ""


def summarize_with_llm(records: list[MemoryRecord], model_name: str = "gpt-4o-mini") -> str:
    """Use LLM to summarize records. Returns summary or fallback to extractive on failure."""
    text = summarize_extractive(records, max_chars=8000)
    if not text.strip():
        return ""
    try:
        from devsper.utils.models import generate
        prompt = f"""Summarize the following memory entries into a concise summary (2-4 paragraphs).

{text}

Summary:"""
        return generate(model_name, prompt).strip()
    except Exception:
        return summarize_extractive(records, max_chars=MAX_EXTRACTIVE_CHARS)


def summarize(
    records: list[MemoryRecord],
    use_llm: bool = False,
    model_name: str = "gpt-4o-mini",
) -> str:
    """Summarize records. use_llm=False uses extractive only."""
    if not records:
        return ""
    if use_llm:
        return summarize_with_llm(records, model_name=model_name)
    return summarize_extractive(records)
