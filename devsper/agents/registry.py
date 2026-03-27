from __future__ import annotations

from devsper.agents.identity import AgentIdentity


class AgentRegistry:
    """Load and resolve named agent identities from config."""

    def __init__(self, identities: list[AgentIdentity] | None = None):
        self._identities = {a.name: a for a in (identities or [])}

    @classmethod
    def from_config(cls, cfg) -> "AgentRegistry":
        raw = getattr(cfg, "agent_identities", None)
        if raw is None:
            return cls([])
        ids: list[AgentIdentity] = []
        for a in raw:
            if hasattr(a, "model_dump"):
                a = a.model_dump()
            if not isinstance(a, dict):
                continue
            name = str(a.get("name", "")).strip()
            if not name:
                continue
            ids.append(
                AgentIdentity(
                    name=name,
                    persona=str(a.get("persona", "")),
                    model=str(a.get("model", "gpt-4o-mini")),
                    memory_namespace=str(a.get("memory_namespace", name)),
                    tools=list(a.get("tools", [])),
                    max_memory_entries=int(a.get("max_memory_entries", 200)),
                    temperature=float(a.get("temperature", 0.2)),
                )
            )
        return cls(ids)

    def get(self, name: str) -> AgentIdentity | None:
        return self._identities.get(name)

    def assign_to_task(self, task) -> AgentIdentity | None:
        assigned = getattr(task, "agent", None)
        if assigned:
            return self.get(str(assigned))
        return None
