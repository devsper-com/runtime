"""
Async API — run multiple workflows concurrently.

Install: pip install devsper
Run:     python examples/async_example.py
"""

import asyncio
import devsper


async def research(topic: str) -> dict:
    return await devsper.run_async(
        "examples/research.devsper",
        inputs={"topic": topic},
    )


async def main() -> None:
    topics = [
        "sparse autoencoders for LLM interpretability",
        "diffusion models for protein structure prediction",
        "reinforcement learning from human feedback",
    ]

    # Run all three research workflows in parallel
    results = await asyncio.gather(*[research(t) for t in topics])

    for topic, result in zip(topics, results):
        print(f"=== {topic} ===")
        for node_id, output in result.items():
            print(f"[{node_id}] {output[:200]}...")
        print()


if __name__ == "__main__":
    asyncio.run(main())
