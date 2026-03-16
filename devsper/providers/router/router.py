"""
LLMRouter: routes requests by model string (provider:model or bare name), with optional fallback.
"""

from collections.abc import AsyncIterator, Callable

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse

# Event type for fallback (caller can emit to event bus)
PROVIDER_FALLBACK_EVENT = "provider_fallback"


def _parse_model_spec(model: str) -> tuple[str | None, str]:
    """Return (prefix, model_name). prefix is None if no 'provider:' prefix."""
    m = (model or "").strip()
    if ":" in m:
        prefix, name = m.split(":", 1)
        return prefix.strip().lower(), name.strip()
    return None, m


class LLMRouter:
    """
    Holds registered LLMBackend instances. Routes by model string:
    - "ollama:llama3" -> OllamaBackend, model="llama3"
    - "vllm:mistral-7b" -> VLLMBackend, model="mistral-7b"
    - "openai:gpt-4o" -> OpenAIBackend
    - bare "gpt-4o" -> first backend where supports_model("gpt-4o") is True
    """

    def __init__(
        self,
        fallback_order: list[str] | None = None,
        max_fallbacks: int = 2,
        on_fallback: Callable[[dict], None] | None = None,
    ) -> None:
        self._backends: list[LLMBackend] = []
        self._by_name: dict[str, LLMBackend] = {}
        self.fallback_order = fallback_order or []
        self.max_fallbacks = max(0, max_fallbacks)
        self.on_fallback = on_fallback

    def register(self, backend: LLMBackend) -> None:
        """Register a backend. Name must be unique."""
        if backend.name in self._by_name:
            return
        self._backends.append(backend)
        self._by_name[backend.name] = backend

    def _backend_for_prefix(self, prefix: str) -> LLMBackend | None:
        return self._by_name.get(prefix)

    async def _backend_for_bare_model(self, model_name: str) -> LLMBackend | None:
        """First registered backend that supports the bare model name."""
        for b in self._backends:
            if b.supports_model(model_name):
                return b
        return None

    def _order_for_fallback(self, primary_name: str) -> list[LLMBackend]:
        """Backends to try after primary, in fallback_order order."""
        seen = {primary_name}
        out = []
        for name in self.fallback_order:
            if name not in seen and name in self._by_name:
                seen.add(name)
                out.append(self._by_name[name])
        return out

    async def route(self, request: LLMRequest) -> LLMResponse:
        """Route request to the appropriate backend. On failure, try fallback chain."""
        prefix, model_name = _parse_model_spec(request.model)
        primary: LLMBackend | None = None
        if prefix is not None:
            primary = self._backend_for_prefix(prefix)
            if primary is not None:
                req = LLMRequest(
                    model=model_name,
                    messages=request.messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    tools=request.tools,
                    stream=False,
                )
            else:
                primary = await self._backend_for_bare_model(request.model)
                req = request
        else:
            primary = await self._backend_for_bare_model(model_name or request.model)
            req = request

        if primary is None:
            raise ValueError(f"No backend for model: {request.model}")

        fallbacks = self._order_for_fallback(primary.name)[: self.max_fallbacks]
        last_error = None
        for backend in [primary] + fallbacks:
            try:
                if backend is not primary and self.on_fallback:
                    self.on_fallback({
                        "original_backend": primary.name,
                        "fallback_backend": backend.name,
                        "reason": str(last_error) if last_error else "unknown",
                    })
                resp = await backend.complete(req)
                return resp
            except Exception as e:
                last_error = e
                continue
        if last_error:
            raise last_error
        raise ValueError(f"No backend could complete request for model: {request.model}")

    async def route_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Route streaming request. Fallback not applied to stream (use complete for retries)."""
        prefix, model_name = _parse_model_spec(request.model)
        backend: LLMBackend | None = None
        req = request
        if prefix is not None:
            backend = self._backend_for_prefix(prefix)
            if backend is not None:
                req = LLMRequest(
                    model=model_name,
                    messages=request.messages,
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                    tools=request.tools,
                    stream=True,
                )
        if backend is None:
            backend = await self._backend_for_bare_model(model_name or request.model)
        if backend is None:
            raise ValueError(f"No backend for model: {request.model}")
        async for chunk in backend.stream(req):
            yield chunk
