"""
Provider router: map model name → provider instance.

Agent and planner call generate(model, prompt) in utils.models;
utils.models uses the router to get the right provider.

When AZURE_OPENAI_ENDPOINT is set, GPT models use Azure OpenAI (model name = deployment name).
When AZURE_ANTHROPIC_ENDPOINT (or AZURE_ANTHROPIC_API_KEY) is set, Claude models use Azure Foundry.
"""

import os

from dotenv import load_dotenv

from hivemind.providers.base import BaseProvider, MockProvider
from hivemind.providers.openai import OpenAIProvider
from hivemind.providers.anthropic import AnthropicProvider
from hivemind.providers.gemini import GeminiProvider
from hivemind.providers.github import GitHubProvider

load_dotenv()

# Provider prefix in model spec (provider:model)
PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "azure": OpenAIProvider,  # Azure OpenAI uses OpenAIProvider with azure=True
    "gemini": GeminiProvider,
    "github": GitHubProvider,
}


def _parse_model_spec(model: str) -> tuple[str, str]:
    """Return (vendor, model_name). If 'provider:model' format, vendor is provider; else infer from name."""
    m = (model or "").strip()
    if ":" in m:
        vendor, name = m.split(":", 1)
        return vendor.strip().lower(), name.strip()
    return _model_to_vendor(m), m


def _model_to_vendor(model: str) -> str:
    """Return 'openai' | 'anthropic' | 'gemini' | 'github' | 'mock' from model name (no prefix)."""
    m = (model or "").strip().lower()
    if m in ("mock", "default", ""):
        return "mock"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    return "mock"


def _use_azure_openai() -> bool:
    """True when Azure OpenAI env vars are set (endpoint + key)."""
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"))


class ProviderRouter:
    """Maps model name (or provider:model) to provider. Caches one instance per vendor."""

    def __init__(self) -> None:
        self._openai: OpenAIProvider | None = None
        self._anthropic: AnthropicProvider | None = None
        self._gemini: GeminiProvider | None = None
        self._github: GitHubProvider | None = None
        self._mock = MockProvider()

    def get_provider(self, model_name: str) -> BaseProvider:
        """Return the provider that should handle this model name (supports provider:model)."""
        vendor, _ = _parse_model_spec(model_name)
        if vendor == "openai" or vendor == "azure":
            if self._openai is None:
                self._openai = OpenAIProvider(azure=_use_azure_openai())
            return self._openai
        if vendor == "anthropic":
            if self._anthropic is None:
                self._anthropic = AnthropicProvider()
            return self._anthropic
        if vendor == "gemini":
            if self._gemini is None:
                self._gemini = GeminiProvider()
            return self._gemini
        if vendor == "github":
            if self._github is None:
                self._github = GitHubProvider()
            return self._github
        return self._mock


_router: ProviderRouter | None = None


def get_router() -> ProviderRouter:
    """Return the global router (singleton)."""
    global _router
    if _router is None:
        _router = ProviderRouter()
    return _router
