"""Abstract base for message bus backends."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Awaitable, Callable

import asyncio

from devsper.bus.message import BusMessage
from devsper.events import ClarificationRequest, ClarificationResponse


class BusBackend(ABC):
    @abstractmethod
    async def publish(self, message: BusMessage) -> None:
        """Publish a message to the bus."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        handler: Callable[[BusMessage], Awaitable[None]],
        run_id: str | None = None,
    ) -> None:
        """Subscribe to a topic (supports wildcards like task.*). run_id scopes channel when set (Redis)."""
        ...

    @abstractmethod
    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the backend (e.g. connect to Redis)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the backend."""
        ...

    # --- Clarification helpers (distributed HITL) ---

    async def publish_clarification_request(
        self, run_id: str, request: ClarificationRequest, node_id: str
    ) -> None:
        topic = f"clarification.request.{run_id}"
        payload = {
            "request": request.to_dict() if hasattr(request, "to_dict") else dict(request),
            "node_id": node_id,
        }
        from devsper.bus.message import create_bus_message

        await self.publish(
            create_bus_message(
                topic=topic,
                payload=payload,
                sender_id=node_id or "local",
                run_id=run_id,
            )
        )

    async def subscribe_clarification_requests(
        self, run_id: str
    ) -> AsyncIterator[tuple[ClarificationRequest, str]]:
        """
        Async iterator of (ClarificationRequest, node_id).
        Implemented via subscribe() and a local queue so it works for all backends.
        """
        topic = f"clarification.request.{run_id}"
        q: asyncio.Queue = asyncio.Queue()

        async def _handler(msg: BusMessage) -> None:
            payload = getattr(msg, "payload", {}) or {}
            req_raw = payload.get("request") or {}
            node_id = payload.get("node_id") or getattr(msg, "sender_id", "") or "local"
            try:
                req = ClarificationRequest.from_dict(req_raw) if isinstance(req_raw, dict) else ClarificationRequest(**req_raw)
            except Exception:
                try:
                    req = ClarificationRequest(**req_raw)
                except Exception:
                    return
            await q.put((req, str(node_id)))

        await self.subscribe(topic, _handler, run_id=None)
        try:
            while True:
                yield await q.get()
        finally:
            try:
                await self.unsubscribe(topic)
            except Exception:
                pass

    async def publish_clarification_response(
        self, run_id: str, response: ClarificationResponse
    ) -> None:
        topic = f"clarification.response.{run_id}.{response.request_id}"
        from devsper.bus.message import create_bus_message

        payload = {
            "request_id": response.request_id,
            "answers": dict(response.answers or {}),
            "skipped": bool(getattr(response, "skipped", False)),
        }
        await self.publish(
            create_bus_message(
                topic=topic,
                payload=payload,
                sender_id="controller",
                run_id=run_id,
            )
        )

    async def wait_for_clarification_response(
        self, run_id: str, request_id: str, timeout: float
    ) -> ClarificationResponse:
        topic = f"clarification.response.{run_id}.{request_id}"
        fut: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _handler(msg: BusMessage) -> None:
            if fut.done():
                return
            payload = getattr(msg, "payload", {}) or {}
            try:
                resp = ClarificationResponse(
                    request_id=payload.get("request_id", request_id),
                    answers=dict(payload.get("answers", {}) or {}),
                    skipped=bool(payload.get("skipped", False)),
                )
            except Exception:
                resp = ClarificationResponse(request_id=request_id, answers={}, skipped=True)
            fut.set_result(resp)

        await self.subscribe(topic, _handler, run_id=None)
        try:
            return await asyncio.wait_for(fut, timeout=float(timeout))
        except asyncio.TimeoutError:
            return ClarificationResponse(request_id=request_id, answers={}, skipped=True)
        finally:
            try:
                await self.unsubscribe(topic)
            except Exception:
                pass
