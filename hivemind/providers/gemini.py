"""Google Gemini provider adapter using LangChain."""

import os
from typing import Iterator

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from hivemind.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """Google Gemini API adapter. Uses GOOGLE_API_KEY or GEMINI_API_KEY (or pass api_key)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get(
            "GEMINI_API_KEY"
        )
        if not self.api_key:
            raise ValueError("Gemini requires api_key or GOOGLE_API_KEY or GEMINI_API_KEY")

    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        """Call Gemini API and return the model output text."""
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=self.api_key,
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
