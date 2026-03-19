"""
Model invocation layer: generate(model_name, prompt) -> text.

Uses v2 LLMRouter when available (from config), else legacy ProviderRouter.
When model_name is "auto", use resolve_model(spec, task_type) first.
"""

import asyncio

from devsper.providers.model_router import TaskType


def resolve_model(model_spec: str, task_type: TaskType) -> str:
    """If model_spec is 'auto', return model_router.select_model(task_type); else return model_spec."""
    if (model_spec or "").strip().lower() == "auto":
        from devsper.providers.model_router import select_model

        return select_model(task_type)
    return model_spec or "mock"


def _run_async(coro):
    """Run coroutine from sync context (new loop or current)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def generate(model_name: str, prompt: str, stream: bool = False):
    """Call the model with the given prompt and return text output (or stream iterator if stream=True)."""
    if not stream:
        try:
            from devsper.providers.router.factory import get_llm_router
            from devsper.providers.router.base import LLMRequest
            router = get_llm_router()
            if router is not None:
                req = LLMRequest(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                    temperature=0.0,
                    tools=None,
                    stream=False,
                )
                resp = _run_async(router.route(req))
                return resp.content
        except Exception:
            pass
    from devsper.providers.router import get_router

    provider = get_router().get_provider(model_name)
    return provider.generate(model_name, prompt, stream=stream)
