"""Router package: legacy ProviderRouter + v2 LLMRouter."""

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse
from devsper.providers.router.router import LLMRouter
from devsper.providers.router.legacy import (
    ProviderRouter,
    get_router,
    _parse_model_spec,
    _model_to_vendor,
)

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
