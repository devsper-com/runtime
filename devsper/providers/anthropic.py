"""Anthropic provider adapter using LangChain. Supports native Anthropic and Azure (Foundry) Claude."""

import os
from typing import Iterator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from devsper.providers.base import BaseProvider


def _normalize_azure_base_url(url: str) -> str:
    """Strip trailing /messages so base URL ends with /v1; ChatAnthropic will append /messages."""
    if not url:
        return url
    url = url.rstrip("/")
    if url.endswith("/messages"):
        return url[: -len("/messages")]
    return url


class AnthropicProvider(BaseProvider):
    """
    Anthropic API adapter. Uses ANTHROPIC_API_KEY (or pass api_key).
    When AZURE_ANTHROPIC_* env vars are set, uses Azure Foundry Claude endpoint instead.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        azure: bool = False,
        azure_endpoint: str | None = None,
        azure_api_key: str | None = None,
        azure_deployment: str | None = None,
    ) -> None:
        self.azure = azure or bool(
            os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get("AZURE_ANTHROPIC_API_KEY")
        )
        if self.azure:
            self.azure_endpoint = _normalize_azure_base_url(
                azure_endpoint or os.environ.get("AZURE_ANTHROPIC_ENDPOINT", "")
            )
            self.azure_api_key = azure_api_key or os.environ.get("AZURE_ANTHROPIC_API_KEY")
            self.azure_deployment = (azure_deployment or os.environ.get("AZURE_ANTHROPIC_DEPLOYMENT_NAME") or "").strip()
            if not self.azure_endpoint or not self.azure_api_key:
                raise ValueError(
                    "Azure Anthropic requires AZURE_ANTHROPIC_ENDPOINT and AZURE_ANTHROPIC_API_KEY"
                )
            self.api_key = self.azure_api_key
        else:
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
            self.azure_endpoint = ""
            self.azure_api_key = ""
            self.azure_deployment = ""
            if not self.api_key:
                raise ValueError("Anthropic requires api_key or ANTHROPIC_API_KEY")

    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        """Call Anthropic (or Azure Claude) API and return the model output text."""
        if self.azure:
            deployment = (model or self.azure_deployment or "").strip() or self.azure_deployment
            if not deployment:
                raise ValueError("Azure Anthropic requires model name or AZURE_ANTHROPIC_DEPLOYMENT_NAME")
            llm = ChatAnthropic(
                model=deployment,
                anthropic_api_url=self.azure_endpoint,
                anthropic_api_key=self.azure_api_key,
                temperature=0,
            )
        else:
            llm = ChatAnthropic(
                model=model,
                api_key=self.api_key,
                temperature=0,
            )
        message = llm.invoke([HumanMessage(content=prompt)])
        content = message.content
        text = content if isinstance(content, str) else str(content)
        if stream:
            def _gen():
                yield text
            return _gen()
        return text
