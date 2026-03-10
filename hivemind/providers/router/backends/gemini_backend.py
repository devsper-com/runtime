"""Google Gemini LLM backend."""

import os

from hivemind.providers.router.base import LLMBackend, LLMRequest, LLMResponse


def _messages_to_lc(messages: list[dict]) -> list:
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


class GeminiBackend(LLMBackend):
    """Google Gemini API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini requires api_key or GOOGLE_API_KEY or GEMINI_API_KEY")
        self._llm = None

    @property
    def name(self) -> str:
        return "gemini"

    def _get_llm(self, model: str):
        if self._llm is not None:
            return self._llm
        from langchain_google_genai import ChatGoogleGenerativeAI
        self._llm = ChatGoogleGenerativeAI(
            model=model or "gemini-1.5-flash",
            google_api_key=self.api_key,
            temperature=0,
        )
        return self._llm

    def supports_model(self, model_name: str) -> bool:
        return (model_name or "").strip().lower().startswith("gemini")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or "gemini-1.5-flash"
        llm = self._get_llm(model)
        lc_messages = _messages_to_lc(request.messages)
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
        model = request.model or "gemini-1.5-flash"
        llm = self._get_llm(model)
        lc_messages = _messages_to_lc(request.messages)
        async for chunk in llm.astream(lc_messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

    async def health(self) -> bool:
        try:
            await self.complete(
                LLMRequest(model="gemini-1.5-flash", messages=[{"role": "user", "content": "Hi"}], max_tokens=2)
            )
            return True
        except Exception:
            return False
