"""OpenAI + Azure OpenAI LLM backend (LangChain)."""

import os

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from devsper.providers.router.base import LLMBackend, LLMRequest, LLMResponse


def _is_azure_foundry_v1_endpoint(endpoint: str) -> bool:
    """True if endpoint is Azure Foundry v1 (use ChatOpenAI + base_url, not AzureChatOpenAI)."""
    if not endpoint:
        return False
    e = endpoint.rstrip("/").lower()
    return "/openai/v1" in e or "cognitiveservices.azure.com" in e


def _messages_to_lc(messages: list[dict]) -> list:
    out = []
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = m.get("content") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "system":
            out.append(SystemMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out


class OpenAIBackend(LLMBackend):
    """OpenAI API and Azure OpenAI. Uses OPENAI_* / AZURE_OPENAI_* env or constructor args."""

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
        self.azure = azure or bool(
            os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY")
        )
        self.azure_endpoint = (azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "") or "").strip().rstrip("/")
        self.azure_deployment = azure_deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "")
        self.api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
        if self.azure and not self.api_key:
            self.api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        self._azure_foundry = _is_azure_foundry_v1_endpoint(self.azure_endpoint)
        self._llm_cache: dict[str, object] = {}

    @property
    def name(self) -> str:
        return "openai"

    def _get_llm(self, model: str):
        key = model or (self.azure_deployment if self.azure else "gpt-4o")
        if key in self._llm_cache:
            return self._llm_cache[key]
        if self.azure:
            dep = model or self.azure_deployment or "gpt-4o"
            if self._azure_foundry:
                from langchain_openai import ChatOpenAI
                base = self.azure_endpoint if self.azure_endpoint.endswith("/") else self.azure_endpoint + "/"
                llm = ChatOpenAI(
                    base_url=base,
                    api_key=self.api_key,
                    model=dep,
                    temperature=0,
                )
            else:
                from langchain_openai import AzureChatOpenAI
                llm = AzureChatOpenAI(
                    azure_endpoint=self.azure_endpoint,
                    azure_deployment=dep,
                    openai_api_key=self.api_key,
                    api_version=self.api_version,
                    temperature=0,
                )
        else:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model or "gpt-4o",
                api_key=self.api_key,
                temperature=0,
            )
        self._llm_cache[key] = llm
        return llm

    def supports_model(self, model_name: str) -> bool:
        m = (model_name or "").strip().lower()
        if self.azure:
            return True
        return m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or (self.azure_deployment if self.azure else "gpt-4o")
        llm = self._get_llm(model)
        lc_messages = _messages_to_lc(request.messages)
        msg = await llm.ainvoke(lc_messages)
        content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        usage = {}
        if hasattr(msg, "response_metadata") and msg.response_metadata:
            meta = msg.response_metadata.get("usage", {}) or msg.response_metadata
            usage = {
                "prompt_tokens": meta.get("prompt_tokens", meta.get("input_tokens", 0)),
                "completion_tokens": meta.get("completion_tokens", meta.get("output_tokens", 0)),
                "total_tokens": meta.get("total_tokens", 0),
            }
        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            finish_reason="stop",
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        model = request.model or (self.azure_deployment if self.azure else "gpt-4o")
        llm = self._get_llm(model)
        lc_messages = _messages_to_lc(request.messages)
        async for chunk in llm.astream(lc_messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

    async def health(self) -> bool:
        try:
            await self.complete(
                LLMRequest(
                    model="gpt-4o-mini" if not self.azure else (self.azure_deployment or "gpt-4o"),
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=2,
                )
            )
            return True
        except Exception:
            return False
