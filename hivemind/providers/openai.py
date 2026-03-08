"""OpenAI provider adapter. Supports standard OpenAI API and Azure OpenAI."""

import os

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from hivemind.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    """
    OpenAI API adapter. Supports standard OpenAI and Azure OpenAI.

    Standard: OPENAI_API_KEY (or pass api_key). Model passed in generate(model, prompt).
    Azure: set azure=True and azure_endpoint (and optionally azure_deployment for single-deployment).
    When Azure is used, generate(model, prompt) uses model as the deployment name so multiple
    deployments (e.g. gpt-4o, gpt-5-mini) on the same endpoint are supported.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        azure: bool = False,
        azure_endpoint: str | None = None,
        azure_deployment: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.azure = azure
        self.azure_endpoint = azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.azure_deployment = azure_deployment or os.environ.get(
            "AZURE_OPENAI_DEPLOYMENT_NAME"
        )
        self.api_version = api_version or os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2024-05-01-preview"
        )
        if azure:
            if not self.azure_endpoint:
                raise ValueError("Azure requires azure_endpoint or AZURE_OPENAI_ENDPOINT")
            key = self.api_key or os.environ.get("AZURE_OPENAI_API_KEY")
            if not key:
                raise ValueError("Azure requires api_key or AZURE_OPENAI_API_KEY")
            self._azure_key = key
            self._llm: AzureChatOpenAI | None = None
            self._llm_cache: dict[str, AzureChatOpenAI] = {}
        else:
            if not self.api_key:
                raise ValueError("OpenAI requires api_key or OPENAI_API_KEY")
            self._llm = None
            self._llm_cache = {}

    def generate(self, model: str, prompt: str) -> str:
        """Call OpenAI or Azure OpenAI and return the model output text."""
        if self.azure:
            deployment = (model or self.azure_deployment or "").strip() or self.azure_deployment
            if not deployment:
                raise ValueError("Azure requires model name or AZURE_OPENAI_DEPLOYMENT_NAME")
            if deployment not in self._llm_cache:
                self._llm_cache[deployment] = AzureChatOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    azure_deployment=deployment,
                    openai_api_key=self._azure_key,
                    api_version=self.api_version,
                    # omit temperature—some Azure deployments reject it
                )
            message = self._llm_cache[deployment].invoke([HumanMessage(content=prompt)])
        else:
            llm = ChatOpenAI(
                model=model,
                api_key=self.api_key,
                temperature=0,
            )
            message = llm.invoke([HumanMessage(content=prompt)])
        content = message.content
        return content if isinstance(content, str) else str(content)
