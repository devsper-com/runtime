"""
Provider base interface.

All providers implement generate(model, prompt) -> str.
Agent and planner call generate() via utils.models; they do not know the provider.
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Common interface for OpenAI, Anthropic, Gemini, and mock."""

    @abstractmethod
    def generate(self, model: str, prompt: str) -> str:
        """Return model output for the given model name and prompt."""
        ...


class MockProvider(BaseProvider):
    """In-memory provider for tests and default stub. No API key required."""

    def generate(self, model: str, prompt: str) -> str:
        return f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"
