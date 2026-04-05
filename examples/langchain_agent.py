#!/usr/bin/env python3
"""
Run a LangChain agent through Devsper's task wrapper (no swarm planner).

Usage (from runtime/ repo root):
  uv run python examples/langchain_agent.py
  uv run python examples/langchain_agent.py --prompt "Say hello in one word."

With a real model (requires provider key in env / devsper credentials):
  uv run python examples/langchain_agent.py --live --prompt "Name one planet."
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


def _build_agent(live: bool):
    from langchain.agents import create_agent

    if live:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(model=os.environ.get("DEVSPER_LC_MODEL", "gpt-4o-mini"))
        return create_agent(model, tools=[])

    from langchain_core.language_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    model = GenericFakeChatModel(messages=iter([AIMessage(content="ok (fake model)")]))
    return create_agent(model, tools=[])


def main() -> None:
    p = argparse.ArgumentParser(description="LangChain agent via Devsper langchain_adapter")
    p.add_argument("--prompt", default="", help="User message (HumanMessage) when set")
    p.add_argument(
        "--live",
        action="store_true",
        help="Use ChatOpenAI (needs OPENAI_API_KEY); default uses a fake chat model",
    )
    args = p.parse_args()

    async def _run() -> int:
        from langchain_core.messages import HumanMessage

        from devsper.integrations.langchain_adapter import langchain_task, run_langchain_runnable

        agent = _build_agent(args.live)
        messages = []
        if args.prompt.strip():
            messages = [HumanMessage(content=args.prompt.strip())]
        task = langchain_task("lc-1", description="LangChain agent turn")
        out = await run_langchain_runnable(task, agent, {"messages": messages})
        print(out)
        return 0

    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
