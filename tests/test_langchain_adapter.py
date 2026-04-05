"""Tests for LangChain runnable → Devsper task helpers."""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")


@pytest.mark.asyncio
async def test_run_langchain_runnable_dict_output():
    from langchain_core.language_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from devsper.integrations.langchain_adapter import langchain_task, run_langchain_runnable

    model = GenericFakeChatModel(messages=iter([AIMessage(content="x")]))
    chain = RunnableLambda(lambda _inp: {"output": "hello"})
    task = langchain_task("t1")
    out = await run_langchain_runnable(task, chain, {})
    assert out == "hello"
    out2 = await run_langchain_runnable(task, model, [])
    assert "x" in out2
