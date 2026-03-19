"""Router package: legacy ProviderRouter + v2 LLMRouter."""

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse
from devsper.providers.router.router import LLMRouter

__all__ = [
    "LLMBackend",
    "LLMRequest",
    "LLMResponse",
    "LLMRouter",
    "ProviderRouter",
    "get_router",
    "_parse_model_spec",
    "_model_to_vendor",
]


def __getattr__(name: str):
    # Legacy provider router pulls optional provider SDK deps; keep lazy.
    if name in ("ProviderRouter", "get_router", "_parse_model_spec", "_model_to_vendor"):
        from devsper.providers.router import legacy

        return getattr(legacy, name)
    raise AttributeError(name)
