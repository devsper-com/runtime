"""LLM backends for the router."""

from hivemind.providers.router.backends.openai_backend import OpenAIBackend
from hivemind.providers.router.backends.anthropic_backend import AnthropicBackend
from hivemind.providers.router.backends.gemini_backend import GeminiBackend
from hivemind.providers.router.backends.github_backend import GitHubBackend
from hivemind.providers.router.backends.ollama_backend import OllamaBackend
from hivemind.providers.router.backends.vllm_backend import VLLMBackend
from hivemind.providers.router.backends.custom_backend import CustomBackend

__all__ = [
    "OpenAIBackend",
    "AnthropicBackend",
    "GeminiBackend",
    "GitHubBackend",
    "OllamaBackend",
    "VLLMBackend",
    "CustomBackend",
]
