"""LLM backends for the router."""

from devsper.providers.router.backends.openai_backend import OpenAIBackend
from devsper.providers.router.backends.anthropic_backend import AnthropicBackend
from devsper.providers.router.backends.gemini_backend import GeminiBackend
from devsper.providers.router.backends.github_backend import GitHubBackend
from devsper.providers.router.backends.ollama_backend import OllamaBackend
from devsper.providers.router.backends.vllm_backend import VLLMBackend
from devsper.providers.router.backends.custom_backend import CustomBackend

__all__ = [
    "OpenAIBackend",
    "AnthropicBackend",
    "GeminiBackend",
    "GitHubBackend",
    "OllamaBackend",
    "VLLMBackend",
    "CustomBackend",
]
