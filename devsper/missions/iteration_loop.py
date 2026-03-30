from __future__ import annotations

from collections.abc import Callable


class IterationEngine:
    """
    Iterative improvement loop:
        while not quality_threshold:
            execute
            critique
            improve
    """

    def run(
        self,
        execute: Callable[[], str],
        critique: Callable[[str], tuple[float, str]],
        improve: Callable[[str, str], str],
        quality_threshold: float = 0.85,
        max_iterations: int = 5,
    ) -> tuple[str, float, int, list[dict]]:
        candidate = ""
        quality = 0.0
        history: list[dict] = []
        iteration = 0
        while quality < quality_threshold and iteration < max_iterations:
            iteration += 1
            if not candidate:
                candidate = execute()
            quality, feedback = critique(candidate)
            history.append(
                {
                    "iteration": iteration,
                    "quality_score": float(quality),
                    "feedback": feedback,
                }
            )
            if quality >= quality_threshold:
                break
            candidate = improve(candidate, feedback)
        return candidate, float(quality), iteration, history
