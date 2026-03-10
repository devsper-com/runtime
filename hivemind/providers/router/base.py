"""
Abstract LLM router types (v2.0).

LLMBackend: abstract backend interface.
LLMRequest / LLMResponse: unified request/response for all backends.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMRequest:
    """Unified request for any LLM backend."""
    model: str
    messages: list[dict]
    max_tokens: int = 4096
    temperature: float = 0.0
    tools: list[dict] | None = None
    stream: bool = False


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""
    content: str
    model: str
    usage: dict  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str
    backend: str


class LLMBackend(ABC):
    """Abstract backend for LLM completion. All providers implement this."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g. 'openai', 'ollama')."""
        ...

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Non-streaming completion."""
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Streaming completion; yield content chunks."""
        ...

    @abstractmethod
    async def health(self) -> bool:
        """Return True if backend is reachable and usable."""
        ...

    def supports_model(self, model_name: str) -> bool:
        """Return True if this backend can serve the given model (bare name, no prefix)."""
        return False
