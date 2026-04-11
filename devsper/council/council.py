"""
Multi-Model Council: draft → critique → synthesize.

A fast drafter produces a first-pass answer. A powerful critic
identifies gaps, errors, and improvements. A synthesis step
integrates both into the final output.

Activated for high-complexity subtasks (complexity_score >= threshold).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_DRAFTER_SYSTEM = """You are a fast, capable AI assistant.
Given a task, produce a thorough initial answer or implementation.
Be direct and complete. Don't hedge unnecessarily."""

_CRITIC_SYSTEM = """You are a rigorous technical reviewer.
You will receive a task and an initial attempt at solving it.
Identify: gaps, errors, missing edge cases, better approaches, correctness issues.
Be specific. Quote the problematic parts. Suggest concrete improvements.
If the answer is already good, say so briefly."""

_SYNTHESIZER_SYSTEM = """You are a synthesis engine.
Given a task, an initial draft, and a critique of that draft,
produce the final best answer. Incorporate the valid critique points.
Fix identified errors. Keep what was correct in the draft.
Output the final answer directly — no meta-commentary."""


@dataclass
class CouncilConfig:
    """Configuration for the Council strategy."""
    drafter_model: str = "auto"         # fast model for first draft
    critic_model: str = "auto"          # strong model for critique
    synthesizer_model: str = "auto"     # model for final synthesis
    complexity_threshold: int = 3       # min word count / complexity to engage council
    enabled: bool = True
    skip_synthesis: bool = False        # if True, return critic output directly


@dataclass
class CouncilResult:
    task: str
    draft: str
    critique: str
    final: str
    models_used: list[str] = field(default_factory=list)
    council_engaged: bool = True


class Council:
    """
    Executes a task through draft → critique → synthesis.

    Usage::

        council = Council(CouncilConfig(drafter_model="haiku", critic_model="sonnet"))
        result = council.run("Implement a thread-safe LRU cache in Python")
        print(result.final)
    """

    def __init__(self, config: CouncilConfig | None = None) -> None:
        self.config = config or CouncilConfig()

    def should_engage(self, task: str) -> bool:
        """Decide whether the council should be engaged for this task."""
        if not self.config.enabled:
            return False
        # Engage for complex tasks: long description or multi-step indicators
        words = len(task.split())
        multi_step = any(kw in task.lower() for kw in (
            "implement", "refactor", "design", "architect", "optimize",
            "debug", "analyze", "review", "generate", "build", "create",
        ))
        return words >= self.config.complexity_threshold or multi_step

    def run(self, task: str) -> CouncilResult:
        """Run the council synchronously."""
        return asyncio.run(self.arun(task))

    async def arun(self, task: str) -> CouncilResult:
        """Run the full draft → critique → synthesis pipeline."""
        # Step 1: Draft
        log.debug("[council] drafting task (len=%d)", len(task))
        draft = await self._call(
            model=self.config.drafter_model,
            system=_DRAFTER_SYSTEM,
            prompt=f"Task: {task}",
        )

        # Step 2: Critique
        log.debug("[council] critiquing draft")
        critique = await self._call(
            model=self.config.critic_model,
            system=_CRITIC_SYSTEM,
            prompt=f"Task: {task}\n\nInitial draft:\n{draft}",
        )

        # Step 3: Synthesize
        if self.config.skip_synthesis:
            final = draft  # use critic's input as the final (used in testing)
        else:
            log.debug("[council] synthesizing final answer")
            final = await self._call(
                model=self.config.synthesizer_model,
                system=_SYNTHESIZER_SYSTEM,
                prompt=(
                    f"Task: {task}\n\n"
                    f"Initial draft:\n{draft}\n\n"
                    f"Critique:\n{critique}\n\n"
                    f"Now write the final answer:"
                ),
            )

        return CouncilResult(
            task=task,
            draft=draft,
            critique=critique,
            final=final,
            models_used=[
                self.config.drafter_model,
                self.config.critic_model,
                self.config.synthesizer_model,
            ],
        )

    async def _call(self, model: str, system: str, prompt: str) -> str:
        """Make a single LLM call via devsper's router."""
        try:
            from devsper.providers.router.factory import get_llm_router
            from devsper.providers.router.base import LLMRequest

            router = get_llm_router()
            req = LLMRequest(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
                temperature=0.3,
            )
            resp = await router.route(req)
            return resp.content
        except Exception as exc:
            log.warning("[council] LLM call failed (%s): %s", model, exc)
            # Graceful degradation: return empty so synthesizer still runs
            return ""


# ---------------------------------------------------------------------------
# Council-aware task executor helper
# ---------------------------------------------------------------------------

def council_execute(task_description: str, config: CouncilConfig | None = None) -> str:
    """
    Execute a task through the council pipeline.
    Returns the final synthesized answer.
    Falls back to empty string on error.
    """
    try:
        council = Council(config)
        if not council.should_engage(task_description):
            return ""  # caller should use normal execution path
        result = council.run(task_description)
        return result.final
    except Exception as exc:
        log.warning("[council] council_execute failed: %s", exc)
        return ""
