from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading


class HITLState(str, Enum):
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    RESUMED = "resumed"


@dataclass
class HITLSession:
    request_id: str
    task_id: str
    state: HITLState


class HITLCoordinator:
    """Thread-safe state coordinator for pause/await/resume lifecycle."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, HITLSession] = {}

    def request_input(self, request_id: str, task_id: str) -> HITLSession:
        with self._lock:
            session = HITLSession(
                request_id=request_id,
                task_id=task_id,
                state=HITLState.AWAITING_INPUT,
            )
            self._sessions[request_id] = session
            return session

    def resume(self, request_id: str) -> HITLSession | None:
        with self._lock:
            session = self._sessions.get(request_id)
            if session is None:
                return None
            session.state = HITLState.RESUMED
            return session

    def clear(self, request_id: str) -> None:
        with self._lock:
            self._sessions.pop(request_id, None)

    def get(self, request_id: str) -> HITLSession | None:
        with self._lock:
            return self._sessions.get(request_id)

