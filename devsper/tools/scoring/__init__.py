"""
Tool reliability scoring: record results, get scores, blended selection.
"""

from devsper.tools.scoring.store import ToolScore, ToolScoreStore

_default_store: ToolScoreStore | None = None


def get_default_score_store() -> ToolScoreStore:
    """Return the default tool score store (singleton)."""
    global _default_store
    if _default_store is None:
        _default_store = ToolScoreStore()
    return _default_store


def record_tool_result(
    tool_name: str,
    task_type: str | None,
    success: bool,
    latency_ms: int | None = None,
    error_type: str | None = None,
) -> None:
    """Record one tool execution result (success/failure, latency) into the score store."""
    try:
        get_default_score_store().record(
            tool_name=tool_name,
            task_type=task_type,
            success=success,
            latency_ms=latency_ms,
            error_type=error_type,
        )
    except Exception:
        pass


def get_tool_score(tool_name: str) -> ToolScore | None:
    """Return the current ToolScore for a tool, or None if not tracked."""
    try:
        return get_default_score_store().get_score(tool_name)
    except Exception:
        return None


__all__ = [
    "record_tool_result",
    "get_tool_score",
    "get_default_score_store",
    "ToolScoreStore",
    "ToolScore",
]
