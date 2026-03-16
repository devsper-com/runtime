#!/usr/bin/env python3
"""
Quick test for the v2 LLM Router.

Run from repo root. Requires at least one backend:
  - OPENAI_API_KEY set, or
  - Ollama running + [providers.ollama] enabled = true in devsper.toml
"""
import asyncio
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from devsper.providers.router.factory import get_llm_router
        from devsper.providers.router.base import LLMRequest
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        return 1

    router = get_llm_router()
    if router is None:
        print(
            "v2 router not used: no backends registered. Set OPENAI_API_KEY (or similar) "
            "or enable [providers.ollama] in devsper.toml with Ollama running.",
            file=sys.stderr,
        )
        return 0  # not a failure; legacy router will be used

    print(f"v2 LLMRouter active with {len(router._backends)} backend(s): {[b.name for b in router._backends]}")

    async def run() -> None:
        # Prefer ollama if available (no key); else use first registered
        model = "ollama:llama3" if any(b.name == "ollama" for b in router._backends) else None
        if not model:
            if any(b.name == "openai" for b in router._backends):
                model = "openai:gpt-4o-mini"
            elif any(b.name == "anthropic" for b in router._backends):
                model = "anthropic:claude-3-haiku-20240307"
            else:
                model = list(router._backends)[0].name + ":default"
        req = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: v2 router OK"}],
            max_tokens=50,
            temperature=0,
            stream=False,
        )
        resp = await router.route(req)
        print(f"Backend: {resp.backend}, model: {resp.model}")
        print(f"Content: {resp.content[:200]}")
        print(f"Usage: {resp.usage}")

    asyncio.run(run())
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
