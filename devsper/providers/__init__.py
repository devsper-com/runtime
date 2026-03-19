"""Provider adapters: base interface, router, and implementations."""

from devsper.providers.base import BaseProvider, MockProvider

__all__ = [
    "BaseProvider",
    "MockProvider",
    "ProviderRouter",
    "get_router",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
]


def __getattr__(name: str):
    # Keep import lightweight: provider SDK deps are optional in many environments/tests.
    if name in ("ProviderRouter", "get_router"):
        from devsper.providers.router import ProviderRouter, get_router

        return ProviderRouter if name == "ProviderRouter" else get_router
    if name == "OpenAIProvider":
        from devsper.providers.openai import OpenAIProvider

        return OpenAIProvider
    if name == "AnthropicProvider":
        from devsper.providers.anthropic import AnthropicProvider

        return AnthropicProvider
    if name == "GeminiProvider":
        from devsper.providers.gemini import GeminiProvider

        return GeminiProvider
    raise AttributeError(name)
