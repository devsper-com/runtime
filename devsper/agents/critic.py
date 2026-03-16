"""
Critic agent: lightweight second-pass reviewer that scores task results and optionally requests retry.
Always runs on a fast/cheap model. v1.7.
"""

import json
import re
from dataclasses import dataclass

from devsper.types.task import Task
from devsper.utils.models import generate


@dataclass
class CritiqueResult:
    score: float
    issues: list[str]
    retry: bool
    raw: str


class CriticAgent:
    """
    Lightweight second-pass agent that scores a task result and optionally
    requests a retry. Always runs on a fast/cheap model.
    """

    ELIGIBLE_ROLES = {"research", "analysis", "code", "backend", "frontend"}
    SCORE_THRESHOLD = 0.70  # below this, request retry
    MAX_CRITIQUES = 1  # never critique more than once per task

    CRITIC_SYSTEM = """You are a quality reviewer. Score this task result 0.0-1.0 on:
- completeness (did it address the task fully?),
- accuracy (are claims reasonable?),
- actionability (is the output usable?).

Respond ONLY with JSON: {"score": 0.0-1.0, "issues": ["...", ...], "retry": true/false}
Set retry=true only if score < 0.70 AND there are fixable issues."""

    def __init__(self, event_log=None):
        self.event_log = event_log

    async def critique(self, task: Task, result: str, model: str) -> CritiqueResult:
        user_part = f"Task: {task.description}\n\nResult: {(result or '')[:8000]}"
        full_prompt = f"{self.CRITIC_SYSTEM}\n\nUser:\n{user_part}"
        raw = generate(model, full_prompt)
        return self._parse_critique(raw or "{}")

    def _parse_critique(self, raw: str) -> CritiqueResult:
        try:
            # Extract JSON from response (allow markdown code fence)
            stripped = raw.strip()
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
            else:
                data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return CritiqueResult(
                score=1.0,
                issues=[],
                retry=False,
                raw=raw,
            )
        score = float(data.get("score", 1.0))
        issues = list(data.get("issues", [])) if isinstance(data.get("issues"), list) else []
        retry = bool(data.get("retry", False))
        return CritiqueResult(score=score, issues=issues, retry=retry, raw=raw)

    async def get_retry_prompt(
        self, task: Task, result: str, critique: CritiqueResult
    ) -> str:
        """Build retry prompt: original task + critique feedback."""
        feedback = "\n".join(f"- {i}" for i in critique.issues[:10]) if critique.issues else "Quality issues identified."
        return (
            f"{task.description}\n\n"
            f"--- Critique (score {critique.score:.2f}) ---\n"
            f"{feedback}\n\n"
            f"Please improve your response addressing the above. Your previous attempt:\n{result[:2000]}"
        )
