"""GitHub Models provider (GitHub Models API at models.github.ai)."""

import json
import os
from typing import Iterator

import httpx

from hivemind.providers.base import BaseProvider

# GitHub Models API (replaces deprecated models.inference.ai.azure.com)
# Docs: https://docs.github.com/en/rest/models/inference
GITHUB_MODELS_BASE = "https://models.github.ai"
GITHUB_MODELS_CHAT_URL = f"{GITHUB_MODELS_BASE}/inference/chat/completions"
GITHUB_API_VERSION = "2022-11-28"

# Default model when user selects "copilot" or "github:copilot" (publisher/model format)
DEFAULT_GITHUB_MODEL = "openai/gpt-4.1"


def _normalize_model_id(model: str) -> str:
    """Return API model ID: publisher/name. 'copilot' or 'github:copilot' -> default; else strip github: prefix."""
    s = model.split(":", 1)[-1].strip() if ":" in model else model.strip()
    if not s or s.lower() == "copilot":
        return DEFAULT_GITHUB_MODEL
    return s


class GitHubProvider(BaseProvider):
    """
    GitHub Models API adapter (models.github.ai).
    Uses GITHUB_TOKEN with models:read scope (fine-grained PAT or classic).
    """

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub provider requires GITHUB_TOKEN")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

    def generate(
        self, model: str, prompt: str, stream: bool = False
    ) -> str | Iterator[str]:
        """Call GitHub Models inference/chat/completions and return the assistant message content."""
        api_model = _normalize_model_id(model)
        if stream:
            return self._generate_stream(api_model, prompt)
        return self._generate_sync(api_model, prompt)

    def _generate_sync(self, model: str, prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                GITHUB_MODELS_CHAT_URL,
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        return content if isinstance(content, str) else str(content or "")

    def _generate_stream(self, model: str, prompt: str) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": True,
        }
        with httpx.Client(timeout=60.0) as client:
            with client.stream(
                "POST",
                GITHUB_MODELS_CHAT_URL,
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.strip():
                        continue
                    if line.startswith("data: "):
                        chunk = line[6:].strip()
                        if chunk == "[DONE]":
                            break
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
