"""Custom OpenAI-compatible endpoint backend."""

import httpx

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = m.get("content") or ""
        out.append({"role": role, "content": content})
    return out


class CustomBackend(LLMBackend):
    """Any OpenAI-compatible endpoint (base_url, optional api_key, optional model_prefix_strip)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model_prefix_strip: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_prefix_strip = (model_prefix_strip or "").strip() or None

    @property
    def name(self) -> str:
        return "custom"

    def _model_for_request(self, model: str) -> str:
        if self.model_prefix_strip and model.startswith(self.model_prefix_strip):
            return model[len(self.model_prefix_strip):].lstrip("-")
        return model

    def supports_model(self, model_name: str) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self._model_for_request(request.model or "gpt-4o")
        messages = _messages_to_openai(request.messages)
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.tools:
            payload["tools"] = request.tools
        url = f"{self.base_url}/v1/chat/completions"
        from devsper.utils.http import ssl_verify, format_retry_after
        async with httpx.AsyncClient(timeout=120.0, verify=ssl_verify()) as client:
            r = await client.post(url, headers=self._headers(), json=payload)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                hint = format_retry_after(e.response)
                if hint:
                    raise httpx.HTTPStatusError(
                        str(e) + hint, request=e.request, response=e.response
                    ) from e
                raise
            data = r.json()
        choices = data.get("choices") or []
        content = ""
        finish_reason = "stop"
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content") or ""
            finish_reason = choices[0].get("finish_reason") or "stop"
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=model,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=finish_reason,
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        model = self._model_for_request(request.model or "gpt-4o")
        messages = _messages_to_openai(request.messages)
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        url = f"{self.base_url}/v1/chat/completions"
        from devsper.utils.http import ssl_verify, format_retry_after
        async with httpx.AsyncClient(timeout=120.0, verify=ssl_verify()) as client:
            async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    hint = format_retry_after(e.response)
                    if hint:
                        raise httpx.HTTPStatusError(
                            str(e) + hint, request=e.request, response=e.response
                        ) from e
                    raise
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    if line.strip() == "data: [DONE]":
                        return
                    if line.startswith("data: "):
                        import json
                        try:
                            chunk = json.loads(line[6:])
                            choices = chunk.get("choices") or []
                            if choices and choices[0].get("delta", {}).get("content"):
                                yield choices[0]["delta"]["content"]
                        except Exception:
                            pass

    async def health(self) -> bool:
        try:
            await self.complete(
                LLMRequest(model="gpt-4o-mini", messages=[{"role": "user", "content": "Hi"}], max_tokens=2)
            )
            return True
        except Exception:
            return False
