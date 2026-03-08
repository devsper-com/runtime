"""
Provider base interface.

All providers implement generate(model, prompt, stream=False).
When stream=True, yield chunks; when stream=False, return full text.
"""

from abc import ABC, abstractmethod
from typing import Iterator


class BaseProvider(ABC):
    """Common interface for OpenAI, Anthropic, Gemini, GitHub, and mock."""

    @abstractmethod
    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        """Return model output (str or iterator of chunks when stream=True)."""
        ...


def _ensure_str(result) -> str:
    """If result is an iterator (stream=True), consume and return concatenated string."""
    if hasattr(result, "__iter__") and not isinstance(result, str):
        return "".join(result)
    return result if isinstance(result, str) else str(result)


class MockProvider(BaseProvider):
    """In-memory provider for tests and default stub. No API key required."""

    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        text = f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"
        if stream:
            def _gen() -> Iterator[str]:
                yield text
            return _gen()
        return text
