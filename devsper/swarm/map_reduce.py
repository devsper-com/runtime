"""
Map-reduce primitive: partition dataset, parallel map, single reduce.
Uses asyncio + worker pool (same pattern as Executor).
"""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")
A = TypeVar("A")


def map_reduce(
    dataset: list[T],
    map_fn: Callable[[T], R],
    reduce_fn: Callable[[list[R]], A],
    worker_count: int = 4,
) -> A:
    """
    Run map_fn on each item in parallel (up to worker_count concurrent), then reduce_fn on results.

    - dataset: list of items to process
    - map_fn: item -> result (called once per item)
    - reduce_fn: list of results -> aggregated value
    - worker_count: max concurrent map operations

    Returns the result of reduce_fn(map_results).
    """
    import asyncio

    async def _run() -> A:
        sem = asyncio.Semaphore(worker_count)
        loop = asyncio.get_running_loop()
        results: list[R] = [None] * len(dataset)  # type: ignore

        async def _map_one(i: int, item: T) -> None:
            async with sem:
                results[i] = await loop.run_in_executor(None, lambda: map_fn(item))

        await asyncio.gather(*[_map_one(i, item) for i, item in enumerate(dataset)])
        return reduce_fn(results)

    return asyncio.run(_run())
