"""Tests for LangGraph → Devsper task bridging."""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")


def test_compiled_graph_to_tasks_linear():
    from langgraph.graph import END, MessagesState, StateGraph

    from devsper.integrations.langgraph_adapter import compiled_graph_to_tasks

    g = StateGraph(MessagesState)

    def a(_s):
        return {"messages": []}

    def b(_s):
        return {"messages": []}

    g.add_node("a", a)
    g.add_node("b", b)
    g.set_entry_point("a")
    g.add_edge("a", "b")
    g.add_edge("b", END)
    app = g.compile()
    tasks = compiled_graph_to_tasks(app)
    ids = {t.id for t in tasks}
    assert ids == {"a", "b"}
    tb = next(t for t in tasks if t.id == "b")
    assert tb.dependencies == ["a"]


@pytest.mark.asyncio
async def test_run_compiled_graph_as_devsper_tasks_messages_state():
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.graph import END, MessagesState, StateGraph

    from devsper.integrations.langgraph_adapter import run_compiled_graph_as_devsper_tasks

    g = StateGraph(MessagesState)

    def n1(_s):
        return {"messages": [AIMessage(content="one")]}

    def n2(_s):
        return {"messages": [AIMessage(content="two")]}

    g.add_node("n1", n1)
    g.add_node("n2", n2)
    g.set_entry_point("n1")
    g.add_edge("n1", "n2")
    g.add_edge("n2", END)
    app = g.compile()
    out = await run_compiled_graph_as_devsper_tasks(
        app,
        {"messages": [HumanMessage(content="hi")]},
        worker_count=2,
    )
    texts = [getattr(m, "content", str(m)) for m in out["messages"]]
    assert texts == ["hi", "one", "two"]
