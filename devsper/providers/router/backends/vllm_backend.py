"""vLLM backend (OpenAI-compatible endpoint)."""

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse
from devsper.providers.router.backends.custom_backend import CustomBackend


class VLLMBackend(LLMBackend):
    """vLLM server: OpenAI-compatible API with configurable base_url."""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        self._custom = CustomBackend(base_url=base_url, api_key=api_key or None, model_prefix_strip=None)

    @property
    def name(self) -> str:
        return "vllm"

    def supports_model(self, model_name: str) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        resp = await self._custom.complete(request)
        return LLMResponse(
            content=resp.content,
            model=resp.model,
            usage=resp.usage,
            finish_reason=resp.finish_reason,
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        async for chunk in self._custom.stream(request):
            yield chunk

    async def health(self) -> bool:
        return await self._custom.health()
