"""Ollama local LLM backend (http://localhost:11434). No API key required."""

import httpx

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse


class OllamaBackend(LLMBackend):
    """Ollama local. supports_model via GET /api/tags; complete via POST /api/chat."""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")
        self._models_cache: list[str] | None = None

    @property
    def name(self) -> str:
        return "ollama"

    async def _fetch_models(self) -> list[str]:
        if self._models_cache is not None:
            return self._models_cache
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                models = data.get("models") or []
                self._models_cache = [m.get("name", "").split(":")[0] for m in models if m.get("name")]
                return self._models_cache
        except Exception:
            self._models_cache = []
            return []

    def supports_model(self, model_name: str) -> bool:
        """Ollama can serve any model that exists on the server; we rely on prefix 'ollama:' for routing."""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or "llama3"
        messages = request.messages
        prompt = ""
        for m in reversed(messages):
            if (m.get("role") or "user").lower() == "user":
                prompt = m.get("content") or ""
                break
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}] if prompt else [{"role": "user", "content": "Hi"}],
            "stream": False,
            "options": {"num_predict": request.max_tokens, "temperature": request.temperature},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        msg = data.get("message") or {}
        content = msg.get("content") or ""
        usage = data.get("eval_count") or 0
        return LLMResponse(
            content=content,
            model=model,
            usage={"prompt_tokens": 0, "completion_tokens": usage, "total_tokens": usage},
            finish_reason="stop",
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        model = request.model or "llama3"
        prompt = ""
        for m in reversed(request.messages):
            if (m.get("role") or "user").lower() == "user":
                prompt = m.get("content") or ""
                break
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt or "Hi"}],
            "stream": True,
            "options": {"num_predict": request.max_tokens, "temperature": request.temperature},
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    import json
                    try:
                        data = json.loads(line)
                        msg = data.get("message") or {}
                        part = msg.get("content")
                        if part:
                            yield part
                        if data.get("done"):
                            break
                    except Exception:
                        pass

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
