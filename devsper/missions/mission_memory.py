from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class MissionMemory:
    """Mission-scoped memory for findings, decisions, and experiments."""

    research_findings: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    experiments: list[dict] = field(default_factory=list)

    def add_research_finding(self, title: str, content: str) -> None:
        self.research_findings.append(
            {
                "title": title,
                "content": content,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def add_decision(self, decision: str, rationale: str) -> None:
        self.decisions.append(
            {
                "decision": decision,
                "rationale": rationale,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def add_experiment(self, name: str, setup: str, result: str) -> None:
        self.experiments.append(
            {
                "name": name,
                "setup": setup,
                "result": result,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def snapshot(self) -> dict:
        return {
            "research_findings": list(self.research_findings),
            "decisions": list(self.decisions),
            "experiments": list(self.experiments),
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> "MissionMemory":
        return cls(
            research_findings=list(data.get("research_findings", [])),
            decisions=list(data.get("decisions", [])),
            experiments=list(data.get("experiments", [])),
        )

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "MissionMemory":
        if not os.path.isfile(path):
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_snapshot(json.load(f))
