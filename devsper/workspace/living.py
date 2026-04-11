"""
WorkspaceIntelligence — living project model that improves every session.

After each REPL turn, extracts structured facts from the exchange and
stores them in the project's knowledge graph. On session load, relevant
facts are injected as additional context.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from devsper.workspace.context import WorkspaceContext

log = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """You are a knowledge extraction engine for a coding agent.

Given a conversation exchange between a user and an AI coding agent, extract
structured facts about the project. Only extract facts that would be useful
in future sessions — things a developer would want to remember.

Categories to look for:
- architecture: new modules, patterns, data flows discovered or implemented
- command: test/build/run commands mentioned or discovered
- convention: code style, naming conventions, patterns in use
- bug: bugs discovered, error patterns, fragile areas
- api: external APIs, endpoints, interfaces used
- decision: architectural or technical decisions made

Return a JSON array of objects like:
[
  {"category": "architecture", "fact": "AuthService uses JWT with 15min expiry"},
  {"category": "command", "fact": "uv run pytest tests/ -x runs the test suite"},
  ...
]

Return [] if nothing significant to extract.
Return ONLY the JSON array, no explanation."""


class WorkspaceIntelligence:
    """Manages the living project knowledge model for a workspace."""

    def __init__(self, workspace: WorkspaceContext) -> None:
        self.workspace = workspace
        self._store_path = workspace.storage_dir / "intelligence.jsonl"
        workspace.storage_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write path: called after each REPL turn
    # ------------------------------------------------------------------

    def extract_and_store(self, user_message: str, agent_response: str) -> int:
        """Extract facts from an exchange and persist them. Returns count stored."""
        facts = self._extract_facts(user_message, agent_response)
        if not facts:
            return 0
        with self._store_path.open("a", encoding="utf-8") as fh:
            for fact in facts:
                fact["project_id"] = self.workspace.project_id
                fh.write(json.dumps(fact) + "\n")
        log.debug("[living] stored %d facts for project %s", len(facts), self.workspace.project_id)
        return len(facts)

    # ------------------------------------------------------------------
    # Read path: called at session start
    # ------------------------------------------------------------------

    def load_context(self, max_facts: int = 30) -> str:
        """Load recent project facts as a context block."""
        if not self._store_path.exists():
            return ""
        lines = self._store_path.read_text(encoding="utf-8").strip().splitlines()
        # Take most recent max_facts entries
        recent = lines[-max_facts:]
        facts: list[dict] = []
        for line in recent:
            try:
                facts.append(json.loads(line))
            except Exception:
                pass
        if not facts:
            return ""
        by_category: dict[str, list[str]] = {}
        for f in facts:
            cat = f.get("category", "general")
            by_category.setdefault(cat, []).append(f.get("fact", ""))
        lines_out = ["## Learned project knowledge"]
        for cat, items in sorted(by_category.items()):
            lines_out.append(f"### {cat.capitalize()}")
            for item in items[-8:]:  # max 8 per category
                lines_out.append(f"- {item}")
        return "\n".join(lines_out)

    def fact_count(self) -> int:
        """Return total number of stored facts for this project."""
        if not self._store_path.exists():
            return 0
        return sum(1 for _ in self._store_path.open())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_facts(self, user_msg: str, agent_response: str) -> list[dict]:
        """Call LLM to extract facts from the exchange."""
        # Skip if response is too short (likely no useful content)
        if len(agent_response.strip()) < 50:
            return []
        prompt = f"USER: {user_msg[:500]}\n\nAGENT: {agent_response[:2000]}"
        try:
            raw = self._call_llm(prompt, _EXTRACT_SYSTEM)
            # Strip markdown if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.splitlines()[1:])
                if raw.endswith("```"):
                    raw = raw[:-3]
            facts = json.loads(raw)
            if isinstance(facts, list):
                return [f for f in facts if isinstance(f, dict) and "fact" in f]
        except Exception as exc:
            log.debug("[living] fact extraction failed: %s", exc)
        return []

    def _call_llm(self, prompt: str, system: str) -> str:
        from devsper.providers.router.factory import get_llm_router
        from devsper.providers.router.base import LLMRequest
        import asyncio
        router = get_llm_router()
        req = LLMRequest(
            model="auto",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.1,
        )
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(router.route(req))
            return resp.content
        finally:
            loop.close()
