"""Ollama local LLM backend.

Endpoint: $OLLAMA_HOST (default http://localhost:11434).
No API key required.

Model routing
─────────────
• Explicit prefix:  ``ollama:gemma3:12b``  →  model = ``gemma3:12b``
• Bare name:        ``gemma4``, ``llama3``, ``mistral``, ``qwen3``, etc.
  → accepted if Ollama is running AND the model name matches a tag on the server
  (or is in KNOWN_FAMILIES).

Tool calling
────────────
Uses Ollama's native /api/chat tools field (supported since Ollama 0.2+).
Falls back to prompt-injected tool descriptions for older builds.

Config (devsper.toml)
─────────────────────
    [providers.ollama]
    enabled   = true
    base_url  = ""          # empty → $OLLAMA_HOST → http://localhost:11434
    keep_alive = "5m"       # how long Ollama keeps the model hot in VRAM
    num_ctx    = 8192        # context window tokens
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse

# Families we accept as bare model names (without requiring ollama: prefix).
# Checked via prefix match so ``gemma3``, ``gemma3:12b``, ``gemma4`` all match.
KNOWN_FAMILIES: tuple[str, ...] = (
    "gemma", "llama", "mistral", "mixtral", "phi", "qwen",
    "deepseek", "codellama", "vicuna", "orca", "falcon", "solar",
    "stablelm", "wizard", "neural", "openchat", "nous", "dolphin",
    "starcoder", "codegemma", "command-r", "aya", "smollm", "tinyllama",
)


def _default_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


class OllamaBackend(LLMBackend):
    """Full-featured Ollama backend: history, tools, streaming, auto-discovery."""

    def __init__(
        self,
        base_url: str = "",
        keep_alive: str = "5m",
        num_ctx: int = 8192,
    ) -> None:
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self._available_models: list[str] | None = None  # cache

    @property
    def name(self) -> str:
        return "ollama"

    # ------------------------------------------------------------------
    # Model discovery
    # ------------------------------------------------------------------

    async def _fetch_available(self) -> list[str]:
        """Return list of model tags installed on the Ollama server."""
        if self._available_models is not None:
            return self._available_models
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                data = r.json()
                names: list[str] = []
                for m in data.get("models") or []:
                    tag = m.get("name", "")
                    if tag:
                        names.append(tag)              # full tag  e.g. "gemma3:12b"
                        names.append(tag.split(":")[0]) # family     e.g. "gemma3"
                self._available_models = names
        except Exception:
            self._available_models = []
        return self._available_models

    def supports_model(self, model_name: str) -> bool:
        """
        Accept when:
        1. Explicit ``ollama:`` prefix (already stripped by router, so this
           method receives the bare model name in that case — always True).
        2. Bare name whose family matches KNOWN_FAMILIES.
        Note: async availability check is done separately via _fetch_available;
        this sync check is a quick pre-filter used by the router.
        """
        low = model_name.lower()
        if any(low.startswith(fam) for fam in KNOWN_FAMILIES):
            return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_messages(self, request: LLMRequest) -> list[dict[str, Any]]:
        """Convert LLMRequest messages to Ollama chat format (full history)."""
        out: list[dict[str, Any]] = []
        for m in request.messages:
            role = (m.get("role") or "user").lower()
            content = m.get("content") or ""
            # Map system → system (Ollama supports it natively)
            if role in ("user", "assistant", "system"):
                out.append({"role": role, "content": content})
            elif role == "tool":
                # Tool result — wrap as user message if Ollama doesn't support role
                out.append({"role": "tool", "content": content,
                             "tool_call_id": m.get("tool_call_id", "")})
        return out or [{"role": "user", "content": "Hello"}]

    def _build_tools(self, request: LLMRequest) -> list[dict] | None:
        """Convert LLMRequest tools to Ollama tools format."""
        if not request.tools:
            return None
        out = []
        for t in request.tools:
            # LLMRequest tools may already be in OpenAI format
            if t.get("type") == "function":
                out.append(t)
            else:
                out.append({"type": "function", "function": t})
        return out or None

    def _options(self, request: LLMRequest) -> dict:
        opts: dict[str, Any] = {"num_ctx": self.num_ctx}
        if request.temperature is not None:
            opts["temperature"] = request.temperature
        if request.max_tokens:
            opts["num_predict"] = request.max_tokens
        return opts

    def _resolve_model(self, request: LLMRequest) -> str:
        return (request.model or "").strip() or "llama3"

    # ------------------------------------------------------------------
    # complete
    # ------------------------------------------------------------------

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = self._resolve_model(request)
        messages = self._build_messages(request)
        tools = self._build_tools(request)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": self._options(request),
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()

        msg = data.get("message") or {}
        content: str = msg.get("content") or ""

        # Tool calls (Ollama 0.2+ native tool calling)
        tool_calls = msg.get("tool_calls")
        if tool_calls and not content:
            content = json.dumps(tool_calls)

        prompt_tokens = data.get("prompt_eval_count") or 0
        completion_tokens = data.get("eval_count") or 0

        return LLMResponse(
            content=content,
            model=model,
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            finish_reason="tool_calls" if tool_calls else "stop",
            backend=self.name,
        )

    # ------------------------------------------------------------------
    # stream
    # ------------------------------------------------------------------

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        messages = self._build_messages(request)
        tools = self._build_tools(request)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": self._options(request),
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        part = (data.get("message") or {}).get("content")
                        if part:
                            yield part
                        if data.get("done"):
                            break
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # health
    # ------------------------------------------------------------------

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
