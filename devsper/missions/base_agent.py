from __future__ import annotations

from dataclasses import dataclass

from devsper.utils.models import generate


@dataclass(slots=True)
class MissionAgent:
    name: str
    role_prompt: str
    model_name: str = "auto"

    def run(self, goal: str, current: str = "", context: str = "") -> str:
        prompt = (
            f"{self.role_prompt}\n\n"
            f"Goal:\n{goal}\n\n"
            f"Current Draft:\n{current}\n\n"
            f"Context:\n{context}\n\n"
            "Return a concrete, high-quality output."
        )
        return (generate(self.model_name, prompt) or "").strip()
