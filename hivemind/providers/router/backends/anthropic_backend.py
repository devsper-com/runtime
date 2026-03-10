"""Anthropic Claude LLM backend."""

import os

from hivemind.providers.router.base import LLMBackend, LLMRequest, LLMResponse


def _messages_to_anthropic(messages: list[dict]) -> list:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
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


class AnthropicBackend(LLMBackend):
    """Anthropic API (and Azure Foundry when env is set)."""

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
        self.azure_endpoint = (azure_endpoint or os.environ.get("AZURE_ANTHROPIC_ENDPOINT", "")).rstrip("/")
        if self.azure_endpoint.endswith("/messages"):
            self.azure_endpoint = self.azure_endpoint[: -len("/messages")]
        self.api_key = azure_api_key or os.environ.get("AZURE_ANTHROPIC_API_KEY") if self.azure else (api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.azure_deployment = (azure_deployment or os.environ.get("AZURE_ANTHROPIC_DEPLOYMENT_NAME") or "").strip()
        self._llm = None

    @property
    def name(self) -> str:
        return "anthropic"

    def _get_llm(self, model: str):
        if self._llm is not None:
            return self._llm
        from langchain_anthropic import ChatAnthropic
        if self.azure:
            self._llm = ChatAnthropic(
                model=model or self.azure_deployment or "claude-3-5-sonnet-20241022",
                anthropic_api_url=self.azure_endpoint,
                anthropic_api_key=self.api_key,
                temperature=0,
            )
        else:
            self._llm = ChatAnthropic(
                model=model or "claude-3-5-sonnet-20241022",
                api_key=self.api_key,
                temperature=0,
            )
        return self._llm

    def supports_model(self, model_name: str) -> bool:
        return (model_name or "").strip().lower().startswith("claude")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        from langchain_core.messages import HumanMessage
        model = request.model or "claude-3-5-sonnet-20241022"
        llm = self._get_llm(model)
        lc_messages = _messages_to_anthropic(request.messages)
        msg = await llm.ainvoke(lc_messages)
        content = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        usage = {}
        if hasattr(msg, "response_metadata") and msg.response_metadata:
            meta = msg.response_metadata
            usage = {
                "prompt_tokens": meta.get("input_tokens", 0),
                "completion_tokens": meta.get("output_tokens", 0),
                "total_tokens": meta.get("input_tokens", 0) + meta.get("output_tokens", 0),
            }
        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            finish_reason="stop",
            backend=self.name,
        )

    async def stream(self, request: LLMRequest):
        model = request.model or "claude-3-5-sonnet-20241022"
        llm = self._get_llm(model)
        lc_messages = _messages_to_anthropic(request.messages)
        async for chunk in llm.astream(lc_messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

    async def health(self) -> bool:
        try:
            await self.complete(
                LLMRequest(model="claude-3-haiku-20240307", messages=[{"role": "user", "content": "Hi"}], max_tokens=2)
            )
            return True
        except Exception:
            return False
