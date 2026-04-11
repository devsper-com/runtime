from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MissionType(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    EXPERIMENT = "experiment"
    GENERAL = "general"
    RESEARCH_TO_CODE = "research_to_code"


@dataclass(slots=True)
class MissionTask:
    id: str
    title: str
    agent: str
    dependencies: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(slots=True)
class MissionDAG:
    mission_type: MissionType
    goal: str
    tasks: list[MissionTask]

    def as_dict(self) -> dict:
        return {
            "mission_type": self.mission_type.value,
            "goal": self.goal,
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "agent": t.agent,
                    "dependencies": list(t.dependencies),
                    "description": t.description,
                }
                for t in self.tasks
            ],
        }


@dataclass(slots=True)
class MissionCheckpoint:
    mission_id: str
    goal: str
    mission_type: MissionType
    dag: dict
    iteration: int
    quality_score: float
    quality_threshold: float
    run_log: list[dict]
    pending_tasks: list[str]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
