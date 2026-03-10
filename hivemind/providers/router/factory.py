"""Build LLMRouter from config and register backends."""

from hivemind.config import get_config
from hivemind.providers.router.router import LLMRouter
from hivemind.providers.router.backends.openai_backend import OpenAIBackend
from hivemind.providers.router.backends.anthropic_backend import AnthropicBackend
from hivemind.providers.router.backends.gemini_backend import GeminiBackend
from hivemind.providers.router.backends.github_backend import GitHubBackend
from hivemind.providers.router.backends.ollama_backend import OllamaBackend
from hivemind.providers.router.backends.vllm_backend import VLLMBackend
from hivemind.providers.router.backends.custom_backend import CustomBackend

_router_instance: LLMRouter | None = None


def _emit_fallback(payload: dict) -> None:
    try:
        from hivemind.types.event import Event, events
        from hivemind.utils.event_logger import EventLog
        from datetime import datetime, timezone
        from hivemind.config import get_config
        log = EventLog(events_folder_path=get_config().events_dir)
        log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=events.PROVIDER_FALLBACK, payload=payload)
        )
    except Exception:
        pass


def get_llm_router() -> LLMRouter | None:
    """Build and return the v2 LLMRouter from config. Cached. Returns None if not configured."""
    global _router_instance
    if _router_instance is not None:
        return _router_instance
    try:
        cfg = get_config()
        pc = cfg.providers
    except Exception:
        return None
    fallback_order = getattr(pc, "fallback_order", None) or []
    router = LLMRouter(
        fallback_order=fallback_order,
        max_fallbacks=2,
        on_fallback=_emit_fallback,
    )
    # Register standard backends when env/config allows
    import os
    if os.environ.get("OPENAI_API_KEY") or (os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY")):
        try:
            router.register(OpenAIBackend())
        except Exception:
            pass
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AZURE_ANTHROPIC_API_KEY") or os.environ.get("AZURE_ANTHROPIC_ENDPOINT"):
        try:
            router.register(AnthropicBackend())
        except Exception:
            pass
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        try:
            router.register(GeminiBackend())
        except Exception:
            pass
    if os.environ.get("GITHUB_TOKEN"):
        try:
            router.register(GitHubBackend())
        except Exception:
            pass
    if getattr(pc, "ollama", None) and getattr(pc.ollama, "enabled", False):
        try:
            router.register(OllamaBackend(base_url=pc.ollama.base_url or "http://localhost:11434"))
        except Exception:
            pass
    if getattr(pc, "vllm", None) and getattr(pc.vllm, "enabled", False):
        try:
            router.register(VLLMBackend(base_url=pc.vllm.base_url or "http://localhost:8000", api_key=pc.vllm.api_key or ""))
        except Exception:
            pass
    if getattr(pc, "custom", None) and getattr(pc.custom, "enabled", False) and getattr(pc.custom, "base_url", ""):
        try:
            router.register(
                CustomBackend(
                    base_url=pc.custom.base_url,
                    api_key=pc.custom.api_key or None,
                    model_prefix_strip=pc.custom.model_prefix_strip or None,
                )
            )
        except Exception:
            pass
    if not router._backends:
        return None
    _router_instance = router
    return _router_instance
