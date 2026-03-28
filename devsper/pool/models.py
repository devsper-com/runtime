from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"


class PoolTier(str, Enum):
    DEDICATED = "dedicated"
    ORG = "org"
    GLOBAL = "global"
    LOCAL = "local"


@dataclass
class WorkerRecord:
    worker_id: str
    node_id: str
    org_id: Optional[str]
    tier: PoolTier
    status: WorkerStatus = WorkerStatus.IDLE
    current_task: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    profile: str = "prod"


@dataclass
class NodeRecord:
    node_id: str
    org_id: Optional[str]
    tier: PoolTier
    max_workers: int = 4
    workers: list[str] = field(default_factory=list)
    profile: str = "prod"


@dataclass
class QueuedTask:
    task_id: str
    org_id: str
    user_id: str
    priority: int
    payload_enc: bytes
    queued_at: float = field(default_factory=time.time)
    attempts: int = 0

