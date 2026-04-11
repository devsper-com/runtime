"""
Research→Code Bridge — a two-phase mission that connects research findings
directly to code implementation.

Phase 1 (Research): Gather relevant repos, papers, APIs, patterns, and code examples.
           Produce a structured ResearchHandoff.
Phase 2 (Code):     Implement from the handoff — the coder has full research context,
           not just a raw goal.

This is a core novelty: research and coding are unified in a single pipeline
rather than two separate disconnected tools.

Usage::

    mission = ResearchToCodeMission()
    result = mission.run("Build a rate limiter using the token bucket algorithm")
    print(result.final_code)
"""

from __future__ import annotations

import json
import secrets
import logging
from dataclasses import dataclass, field
from pathlib import Path

from devsper.missions.base_agent import MissionAgent
from devsper.missions.models import MissionType
from devsper.utils.models import generate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured handoff between research and coding phases
# ---------------------------------------------------------------------------

@dataclass
class ResearchHandoff:
    """Structured output of the research phase, consumed by the coding phase."""
    goal: str
    summary: str                          # 2-3 sentence synthesis
    patterns: list[str] = field(default_factory=list)     # key patterns/algorithms to use
    code_examples: list[str] = field(default_factory=list) # relevant code snippets found
    apis: list[str] = field(default_factory=list)          # APIs / libraries to leverage
    warnings: list[str] = field(default_factory=list)      # pitfalls / anti-patterns
    references: list[str] = field(default_factory=list)    # repos, papers, docs cited

    def to_context(self) -> str:
        """Format as an LLM-readable context block."""
        parts = [f"## Research Findings for: {self.goal}", f"\n{self.summary}"]
        if self.patterns:
            parts.append("\n### Key Patterns")
            parts.extend(f"- {p}" for p in self.patterns)
        if self.apis:
            parts.append("\n### Libraries / APIs to Use")
            parts.extend(f"- {a}" for a in self.apis)
        if self.code_examples:
            parts.append("\n### Relevant Code Examples")
            for ex in self.code_examples[:3]:
                parts.append(f"```\n{ex[:500]}\n```")
        if self.warnings:
            parts.append("\n### Pitfalls to Avoid")
            parts.extend(f"- {w}" for w in self.warnings)
        if self.references:
            parts.append("\n### References")
            parts.extend(f"- {r}" for r in self.references)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Specialized agents for the bridge pipeline
# ---------------------------------------------------------------------------

_RESEARCH_PROMPT = """You are a deep research agent specializing in software patterns,
algorithms, and implementation strategies.

Given a coding goal, research:
1. The best algorithms and patterns to solve it
2. Key libraries or APIs to leverage (prefer standard library / well-known packages)
3. Concrete code examples (from your training knowledge) that demonstrate the approach
4. Common pitfalls and anti-patterns to avoid
5. References to well-known implementations or documentation

Return a JSON object with this exact schema:
{{
  "summary": "2-3 sentence synthesis of the best approach",
  "patterns": ["pattern1", "pattern2", ...],
  "apis": ["library1.module", "library2", ...],
  "code_examples": ["code snippet 1", "code snippet 2"],
  "warnings": ["pitfall 1", "pitfall 2"],
  "references": ["CPython docs: threading.Lock", "PEP 3156: asyncio", ...]
}}

Return ONLY the JSON object."""

_CODER_PROMPT = """You are an expert software engineer implementing production-quality code.

You have been given a coding goal AND detailed research findings.
Use the research findings to guide your implementation:
- Apply the recommended patterns
- Use the suggested APIs and libraries
- Follow the code examples as reference
- Avoid the listed pitfalls

Implement the solution completely. Include:
- Full working code
- Clear comments for non-obvious logic
- Basic error handling
- A usage example at the bottom

Return the implementation directly."""

_REVIEWER_PROMPT = """You are a senior code reviewer.
Review the implementation against the original goal and research findings.
Check for: correctness, edge cases, adherence to the patterns, missed pitfalls.
If changes are needed, return the corrected code.
If it looks good, return it unchanged with "# LGTM" at the top."""


class ResearchAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="research_agent",
            role_prompt=_RESEARCH_PROMPT,
            model_name=model_name,
        )

    def research(self, goal: str) -> ResearchHandoff:
        """Run research phase and return structured handoff."""
        prompt = f"{_RESEARCH_PROMPT}\n\nCoding Goal: {goal}"
        raw = generate(self.model_name, prompt) or "{}"
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:])
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("[r2c] research agent returned non-JSON, using raw as summary")
            data = {"summary": raw[:500]}
        return ResearchHandoff(
            goal=goal,
            summary=data.get("summary", ""),
            patterns=data.get("patterns", []),
            code_examples=data.get("code_examples", []),
            apis=data.get("apis", []),
            warnings=data.get("warnings", []),
            references=data.get("references", []),
        )


class BridgedCoderAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="bridged_coder_agent",
            role_prompt=_CODER_PROMPT,
            model_name=model_name,
        )

    def implement(self, goal: str, handoff: ResearchHandoff) -> str:
        """Implement from research handoff."""
        prompt = (
            f"Goal: {goal}\n\n"
            f"{handoff.to_context()}\n\n"
            f"Now implement the solution:"
        )
        return (generate(self.model_name, prompt) or "").strip()


class CodeReviewerAgent(MissionAgent):
    def __init__(self, model_name: str = "auto") -> None:
        super().__init__(
            name="code_reviewer_agent",
            role_prompt=_REVIEWER_PROMPT,
            model_name=model_name,
        )

    def review(self, goal: str, code: str, handoff: ResearchHandoff) -> str:
        prompt = (
            f"Original Goal: {goal}\n\n"
            f"{handoff.to_context()}\n\n"
            f"Implementation to review:\n```\n{code}\n```\n\n"
            "Review and return the final code:"
        )
        return (generate(self.model_name, prompt) or code).strip()


# ---------------------------------------------------------------------------
# Main mission class
# ---------------------------------------------------------------------------

@dataclass
class ResearchToCodeResult:
    mission_id: str
    goal: str
    handoff: ResearchHandoff
    initial_code: str
    final_code: str
    reviewed: bool = False


class ResearchToCodeMission:
    """
    Two-phase autonomous mission: research → code.

    Phase 1: ResearchAgent gathers patterns, APIs, examples → ResearchHandoff
    Phase 2: BridgedCoderAgent implements from handoff → reviewed by CodeReviewerAgent

    Produces significantly better code than a direct "implement X" prompt because
    the coder has structured research context, not just a raw goal.
    """

    def __init__(
        self,
        model_name: str = "auto",
        run_review: bool = True,
        checkpoints_dir: str = ".devsper/missions",
    ) -> None:
        self._model = model_name
        self._run_review = run_review
        self._checkpoints_dir = Path(checkpoints_dir)

    def run(self, goal: str) -> ResearchToCodeResult:
        """Run the full research → code pipeline."""
        mission_id = f"r2c_{secrets.token_hex(4)}"
        log.info("[r2c] starting mission %s: %s", mission_id, goal[:80])

        # Phase 1: Research
        log.info("[r2c] phase 1: research")
        researcher = ResearchAgent(model_name=self._model)
        handoff = researcher.research(goal)
        log.info("[r2c] research complete: %d patterns, %d APIs, %d examples",
                 len(handoff.patterns), len(handoff.apis), len(handoff.code_examples))

        # Phase 2: Implement
        log.info("[r2c] phase 2: implementation")
        coder = BridgedCoderAgent(model_name=self._model)
        initial_code = coder.implement(goal, handoff)

        # Phase 3: Review (optional)
        final_code = initial_code
        reviewed = False
        if self._run_review and initial_code:
            log.info("[r2c] phase 3: code review")
            reviewer = CodeReviewerAgent(model_name=self._model)
            final_code = reviewer.review(goal, initial_code, handoff)
            reviewed = True

        result = ResearchToCodeResult(
            mission_id=mission_id,
            goal=goal,
            handoff=handoff,
            initial_code=initial_code,
            final_code=final_code,
            reviewed=reviewed,
        )
        self._checkpoint(result)
        return result

    def _checkpoint(self, result: ResearchToCodeResult) -> None:
        try:
            self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
            path = self._checkpoints_dir / f"{result.mission_id}.json"
            path.write_text(json.dumps({
                "mission_id": result.mission_id,
                "goal": result.goal,
                "handoff": {
                    "summary": result.handoff.summary,
                    "patterns": result.handoff.patterns,
                    "apis": result.handoff.apis,
                    "warnings": result.handoff.warnings,
                    "references": result.handoff.references,
                },
                "final_code_preview": result.final_code[:500],
                "reviewed": result.reviewed,
            }, indent=2), encoding="utf-8")
        except Exception:
            pass
