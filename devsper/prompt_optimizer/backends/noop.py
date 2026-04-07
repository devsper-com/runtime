"""
No-op optimizer: returns the base prompt unchanged.
Default when no optimizer is configured.
"""

from __future__ import annotations

from devsper.prompt_optimizer.base import OptimizeRequest, OptimizeResult, PromptOptimizerBackend


class NoopBackend(PromptOptimizerBackend):
    """Passthrough — useful as a default and for testing."""

    @property
    def name(self) -> str:
        return "noop"

    async def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        return OptimizeResult(
            optimized_prompt=request.base_prompt,
            backend=self.name,
        )

    async def health(self) -> bool:
        return True
