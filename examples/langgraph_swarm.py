#!/usr/bin/env python3
"""
Run a small LangGraph as a Devsper task DAG: each graph node is one schedulable unit.

Uses list-merge state (see `default_list_merge_state`) so `MessagesState`-style graphs behave
when nodes run with parallel branches.

Usage (from runtime/ repo root):
  uv run python examples/langgraph_swarm.py
  uv run python examples/langgraph_swarm.py --workers 8
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _build_graph():
    from langgraph.graph import END, MessagesState, StateGraph
    from langchain_core.messages import AIMessage

    g = StateGraph(MessagesState)

    def n_plan(state: dict):
        return {"messages": [AIMessage(content="[plan] split work")]}

    def n_branch_a(state: dict):
        return {"messages": [AIMessage(content="[branch-a] detail")]}

    def n_branch_b(state: dict):
        return {"messages": [AIMessage(content="[branch-b] detail")]}

    def n_merge(state: dict):
        return {"messages": [AIMessage(content="[merge] done")]}

    g.add_node("plan", n_plan)
    g.add_node("branch_a", n_branch_a)
    g.add_node("branch_b", n_branch_b)
    g.add_node("merge", n_merge)
    g.set_entry_point("plan")
    g.add_edge("plan", "branch_a")
    g.add_edge("plan", "branch_b")
    g.add_edge("branch_a", "merge")
    g.add_edge("branch_b", "merge")
    g.add_edge("merge", END)
    return g.compile()


async def run_async(workers: int) -> int:
    from langchain_core.messages import HumanMessage

    from devsper.integrations.langgraph_adapter import run_compiled_graph_as_devsper_tasks

    app = _build_graph()
    initial = {"messages": [HumanMessage(content="start")]}
    final_state = await run_compiled_graph_as_devsper_tasks(
        app,
        initial,
        worker_count=workers,
    )
    for m in final_state.get("messages", []):
        content = getattr(m, "content", m)
        print(content)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="LangGraph nodes as Devsper concurrent tasks")
    p.add_argument("--workers", type=int, default=4, help="Max concurrent LangGraph nodes")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run_async(args.workers)))


if __name__ == "__main__":
    main()
