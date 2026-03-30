from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ClarificationStore:
    """
    Snapshot-backed persistence for pending clarification requests.

    Stored under snapshot["_durability"]["pending_clarifications"].
    """

    key: str = "pending_clarifications"

    def load(self, snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        durability = (snapshot or {}).get("_durability") or {}
        pending = durability.get(self.key) or {}
        return dict(pending) if isinstance(pending, dict) else {}

    def save(self, snapshot: dict[str, Any], pending: dict[str, dict[str, Any]]) -> None:
        durability = snapshot.setdefault("_durability", {})
        durability[self.key] = dict(pending)


@dataclass
class RunStateStore:
    """
    Snapshot-backed persistence for controller run state metadata.

    Stored under snapshot["_durability"]["run_state"].
    """

    key: str = "run_state"

    def load(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        durability = (snapshot or {}).get("_durability") or {}
        val = durability.get(self.key) or {}
        return dict(val) if isinstance(val, dict) else {}

    def save(self, snapshot: dict[str, Any], run_state: dict[str, Any]) -> None:
        durability = snapshot.setdefault("_durability", {})
        durability[self.key] = dict(run_state)

