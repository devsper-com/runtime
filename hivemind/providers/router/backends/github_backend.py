"""GitHub Models LLM backend (models.github.ai)."""

import json
import logging
import os
import time

import httpx

from hivemind.providers.router.base import LLMBackend, LLMRequest, LLMResponse

log = logging.getLogger(__name__)

GITHUB_MODELS_BASE = "https://models.github.ai"
GITHUB_CHAT_URL = f"{GITHUB_MODELS_BASE}/inference/chat/completions"
GITHUB_API_VERSION = "2022-11-28"
DEFAULT_GITHUB_MODEL = "openai/gpt-4.1"
GITHUB_429_MAX_RETRIES = 3
GITHUB_429_BASE_DELAY = 1.0


def _normalize_model_id(model: str) -> str:
    s = model.split(":", 1)[-1].strip() if ":" in model else model.strip()
    if not s or s.lower() == "copilot":
        return DEFAULT_GITHUB_MODEL
    return s


class GitHubBackend(LLMBackend):
    """GitHub Models API. Uses GITHUB_TOKEN."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub backend requires GITHUB_TOKEN")

    @property
    def name(self) -> str:
        return "github"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    def supports_model(self, model_name: str) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        api_model = _normalize_model_id(request.model)
        messages = request.messages
        last_content = ""
        for m in reversed(messages):
            if (m.get("role") or "user").lower() == "user":
                last_content = m.get("content") or ""
                break
        payload = {
            "model": api_model,
            "messages": [{"role": "user", "content": last_content}] if last_content else [{"role": "user", "content": "Hi"}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        from hivemind.utils.http import ssl_verify, format_retry_after
        async with httpx.AsyncClient(timeout=60.0, verify=ssl_verify()) as client:
            for attempt in range(GITHUB_429_MAX_RETRIES):
                try:
                    resp = await client.post(
                        GITHUB_CHAT_URL,
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except httpx.HTTPStatusError as e:
                    retry_hint = format_retry_after(e.response)
                    if e.response.status_code == 429 and attempt < GITHUB_429_MAX_RETRIES - 1:
                        delay = min(GITHUB_429_BASE_DELAY * (2**attempt), 32.0)
                        log.warning(
                            "GitHub 429, retry %s/%s in %.1fs%s",
                            attempt + 1, GITHUB_429_MAX_RETRIES, delay, retry_hint,
                        )
                        time.sleep(delay)
                    else:
                        if retry_hint:
                            raise httpx.HTTPStatusError(
                                str(e) + retry_hint, request=e.request, response=e.response
                            ) from e
                        raise
        choices = data.get("choices") or []
        content = ""
        if choices:
            msg = choices[0].get("message") or {}
            c = msg.get("content")
            if isinstance(c, str):
                content = c
            elif isinstance(c, list):
                parts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                content = "\n".join(parts) if parts else ""
            else:
                content = str(c or "")
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=api_model,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason="stop",
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        api_model = _normalize_model_id(request.model)
        last_content = ""
        for m in reversed(request.messages):
            if (m.get("role") or "user").lower() == "user":
                last_content = m.get("content") or ""
                break
        payload = {
            "model": api_model,
            "messages": [{"role": "user", "content": last_content or "Hi"}],
            "temperature": request.temperature,
            "stream": True,
        }
        from hivemind.utils.http import ssl_verify
        async with httpx.AsyncClient(timeout=60.0, verify=ssl_verify()) as client:
            async with client.stream(
                "POST",
                GITHUB_CHAT_URL,
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.strip():
                        continue
                    if line.startswith("data: "):
                        chunk = line[6:].strip()
                        if chunk == "[DONE]":
                            return
                        try:
                            data = json.loads(chunk)
                            choices = data.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta") or {}
                                part = delta.get("content")
                                if part:
                                    yield part
                        except Exception:
                            pass

    async def health(self) -> bool:
        try:
            await self.complete(
                LLMRequest(model="openai/gpt-4.1", messages=[{"role": "user", "content": "Hi"}], max_tokens=2)
            )
            return True
        except Exception:
            return False
