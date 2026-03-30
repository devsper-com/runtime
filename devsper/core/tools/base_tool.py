from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Unified tool contract used by core runtime wiring."""

    name: str = ""
    description: str = ""
    schema: dict[str, Any] = {}

    @abstractmethod
    async def run(self, **kwargs: Any) -> str:
        """Execute tool asynchronously and return textual output."""

