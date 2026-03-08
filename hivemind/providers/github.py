"""GitHub Models provider (GitHub Copilot API)."""

import json
import os
from typing import Iterator

import httpx

from hivemind.providers.base import BaseProvider

GITHUB_MODELS_BASE = "https://models.inference.ai.azure.com"


class GitHubProvider(BaseProvider):
    """
    GitHub Models API adapter (used by GitHub Copilot).
    Uses GITHUB_TOKEN for authentication.
    """

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub provider requires GITHUB_TOKEN")

    def generate(
        self, model: str, prompt: str, stream: bool = False
    ) -> str | Iterator[str]:
        """Call GitHub Models /chat/completions and return the assistant message content."""
        api_model = model.split(":", 1)[-1].strip() if ":" in model else model
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
                f"{GITHUB_MODELS_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {self.token}"},
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
                f"{GITHUB_MODELS_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {self.token}"},
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
