"""
Per-run pub/sub channel for agent-to-agent messaging. v1.7.
Agents broadcast discoveries; subsequent agents receive them via memory context.
Not persistent — lives only for the duration of a run.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from hivemind.types.event import Event, events


@dataclass
class AgentMessage:
    sender_task_id: str
    content: str
    tags: list[str]
    timestamp: str


class SwarmMessageBus:
    """
    Per-run pub/sub channel. Agents broadcast discoveries;
    all subsequent agents receive them via memory context.
    Not persistent — lives only for the duration of a run.
    """

    def __init__(self, event_log=None):
        self._messages: list[AgentMessage] = []
        self._lock = asyncio.Lock()
        self._event_log = event_log

    def _emit(self, event_type: events, payload: dict) -> None:
        if self._event_log:
            self._event_log.append_event(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    type=event_type,
                    payload=payload,
                )
            )

    async def broadcast(
        self, sender_task_id: str, content: str, tags: list[str] | None = None
    ) -> None:
        """Agent calls this when it discovers something worth sharing."""
        tags = tags or []
        async with self._lock:
            self._messages.append(
                AgentMessage(
                    sender_task_id=sender_task_id,
                    content=content,
                    tags=tags,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
        self._emit(
            events.AGENT_BROADCAST,
            {
                "sender_task_id": sender_task_id,
                "content_preview": (content or "")[:100],
            },
        )

    def broadcast_sync(
        self, sender_task_id: str, content: str, tags: list[str] | None = None
    ) -> None:
        """Synchronous broadcast for use from sync agent.run()."""
        tags = tags or []
        self._messages.append(
            AgentMessage(
                sender_task_id=sender_task_id,
                content=content,
                tags=tags,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        self._emit(
            events.AGENT_BROADCAST,
            {
                "sender_task_id": sender_task_id,
                "content_preview": (content or "")[:100],
            },
        )

    async def get_context(
        self, requesting_task_id: str, max_messages: int = 5
    ) -> str:
        """
        Return formatted string of recent broadcasts for injection into agent prompt.
        Exclude messages from requesting_task_id itself.
        Return most recent max_messages.
        """
        async with self._lock:
            eligible = [
                m
                for m in self._messages
                if m.sender_task_id != requesting_task_id
            ]
            recent = eligible[-max_messages:] if len(eligible) > max_messages else eligible
        if not recent:
            return ""
        lines = ["Shared Discoveries (from other agents in this run):"]
        for m in recent:
            lines.append(f"- [{m.sender_task_id}]: {m.content[:500]}{'...' if len(m.content) > 500 else ''}")
        return "\n".join(lines)

    def get_context_sync(
        self, requesting_task_id: str, max_messages: int = 5
    ) -> str:
        """Synchronous get_context for use from sync agent.run()."""
        eligible = [
            m
            for m in self._messages
            if m.sender_task_id != requesting_task_id
        ]
        recent = eligible[-max_messages:] if len(eligible) > max_messages else eligible
        if not recent:
            return ""
        lines = ["Shared Discoveries (from other agents in this run):"]
        for m in recent:
            lines.append(f"- [{m.sender_task_id}]: {m.content[:500]}{'...' if len(m.content) > 500 else ''}")
        return "\n".join(lines)
