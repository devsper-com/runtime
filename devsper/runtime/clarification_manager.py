import asyncio
import heapq
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from devsper.events import ClarificationRequest, ClarificationResponse


@dataclass
class QueuedClarification:
    request: ClarificationRequest
    queued_at: float = field(default_factory=time.monotonic)
    node_id: str = ""  # which node the agent is on
    future: asyncio.Future = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )
    status: str = "queued"  # queued | active | answered | skipped | timed_out
    sort_key: tuple = field(init=False)

    def __post_init__(self) -> None:
        prio = getattr(self.request, "priority", 1)
        self.sort_key = (int(prio) if prio is not None else 1, self.queued_at)


class ClarificationManager:
    """
    Serializes all clarification requests across all nodes.

    Guarantees:
    - Only ONE clarification is presented to the user at a time
    - Requests are processed in priority order, FIFO within priority
    - While user is answering, new requests queue silently
    - Response is routed back to the exact node+agent that asked
    - Timeout auto-resolves with defaults so runs don't stall
    - Cancellable per task (if task is cancelled, its pending clarifications resolve as skipped)
    """

    def __init__(self, timeout_seconds: int = 120):
        self._heap: list[tuple[int, int, QueuedClarification]] = []
        self._heap_counter = 0
        self._active: QueuedClarification | None = None
        # Use a synchronous lock so `submit()` can enqueue without an initial await.
        # This avoids race conditions in tests that schedule submit() via create_task()
        # and immediately call queue_snapshot() without yielding.
        self._lock = threading.Lock()
        self._signal = asyncio.Event()
        self._default_timeout = timeout_seconds
        self._cancelled_tasks: set[str] = set()

        # Callbacks — set by TUI/controller
        self.on_clarification_ready: Callable[[QueuedClarification], Any] | None = None
        self.on_queue_changed: Callable[[list[dict]], Any] | None = None
        self.on_task_context_update: Callable[[str, str], Any] | None = None  # (task_id, text)

    def submit(
        self,
        request: ClarificationRequest,
        node_id: str = "local",
    ):
        if self.on_clarification_ready is None:
            # In CI / headless controller we auto-resolve with defaults, but warn once per submit.
            try:
                import logging

                logging.getLogger(__name__).warning(
                    "ClarificationManager has no on_clarification_ready callback; using defaults. "
                    "Did you attach a controller-side UI?"
                )
            except Exception:
                pass
        if request.task_id in self._cancelled_tasks:
            return ClarificationResponse(request_id=request.request_id, answers={}, skipped=True)

        queued = QueuedClarification(request=request, node_id=node_id)

        with self._lock:
            heapq.heappush(
                self._heap,
                (queued.sort_key[0], self._heap_counter, queued),
            )
            self._heap_counter += 1
            if self.on_queue_changed:
                self.on_queue_changed(self.queue_snapshot())
            self._signal.set()

        async def _wait() -> ClarificationResponse:
            try:
                response = await asyncio.wait_for(
                    queued.future,
                    timeout=float(request.timeout_seconds or self._default_timeout),
                )
                return response
            except asyncio.TimeoutError:
                queued.status = "timed_out"
                return self._default_response(request)

        return _wait()

    async def run_dispatch_loop(self) -> None:
        while True:
            await self._signal.wait()
            self._signal.clear()

            while True:
                with self._lock:
                    if not self._heap:
                        break
                    _, _, queued = heapq.heappop(self._heap)

                # Small coalescing delay: gives callers a chance to cancel tasks
                # immediately after submission (prevents flashing prompts and
                # avoids races in tests that cancel very quickly).
                await asyncio.sleep(0.05)

                if queued.request.task_id in self._cancelled_tasks:
                    if not queued.future.done():
                        queued.future.set_result(
                            ClarificationResponse(
                                request_id=queued.request.request_id,
                                answers={},
                                skipped=True,
                            )
                        )
                    continue

                if queued.future.done():
                    continue

                queued.status = "active"
                self._active = queued
                if self.on_queue_changed:
                    self.on_queue_changed(self.queue_snapshot())

                if self.on_clarification_ready:
                    await self.on_clarification_ready(queued)
                else:
                    self._resolve_with_defaults(queued)

                self._active = None
                if self.on_queue_changed:
                    self.on_queue_changed(self.queue_snapshot())

    def resolve(self, request_id: str, answers: dict[str, Any]) -> None:
        queued = self._find(request_id)
        if not queued or queued.future.done():
            return
        queued.status = "answered"
        resp = ClarificationResponse(request_id=request_id, answers=answers, skipped=False)

        if self.on_task_context_update:
            try:
                self.on_task_context_update(
                    queued.request.task_id,
                    self._format_context(queued.request, answers),
                )
            except Exception:
                pass

        queued.future.set_result(resp)

    def skip(self, request_id: str) -> None:
        queued = self._find(request_id)
        if not queued or queued.future.done():
            return
        queued.status = "skipped"
        queued.future.set_result(self._default_response(queued.request))

    def cancel_task(self, task_id: str) -> None:
        self._cancelled_tasks.add(task_id)
        # Resolve and remove pending items in heap.
        with self._lock:
            kept: list[tuple[int, int, QueuedClarification]] = []
            for prio, ctr, queued in list(self._heap):
                if queued.request.task_id != task_id:
                    kept.append((prio, ctr, queued))
                    continue
                if not queued.future.done():
                    queued.future.set_result(
                        ClarificationResponse(
                            request_id=queued.request.request_id,
                            answers={},
                            skipped=True,
                        )
                    )
            self._heap = kept
            heapq.heapify(self._heap)
        if self._active and self._active.request.task_id == task_id:
            if not self._active.future.done():
                self._active.future.set_result(
                    ClarificationResponse(
                        request_id=self._active.request.request_id,
                        answers={},
                        skipped=True,
                    )
                )
        # Wake dispatcher so it can skip cancelled items promptly.
        self._signal.set()

    def queue_snapshot(self) -> list[dict]:
        items: list[dict] = []
        if self._active:
            items.append(
                {
                    "request_id": self._active.request.request_id,
                    "role": self._active.request.agent_role,
                    "task_id": self._active.request.task_id,
                    "node_id": self._active.node_id,
                    "status": "active",
                    "queued_at": self._active.queued_at,
                    "priority": getattr(self._active.request, "priority", 1),
                }
            )
        # heap contains (priority, counter, queued)
        heap_sorted = sorted(self._heap, key=lambda t: (t[0], t[1]))
        for prio, _, q in heap_sorted:
            items.append(
                {
                    "request_id": q.request.request_id,
                    "role": q.request.agent_role,
                    "task_id": q.request.task_id,
                    "node_id": q.node_id,
                    "status": "queued",
                    "queued_at": q.queued_at,
                    "priority": prio,
                }
            )
        return items

    def pending_count(self) -> int:
        return len(self._heap) + (1 if self._active else 0)

    def _find(self, request_id: str) -> QueuedClarification | None:
        if self._active and self._active.request.request_id == request_id:
            return self._active
        for _, _, q in self._heap:
            if q.request.request_id == request_id:
                return q
        return None

    def _default_response(self, request: ClarificationRequest) -> ClarificationResponse:
        answers: dict[str, Any] = {}
        for field in request.fields:
            if isinstance(field, dict):
                if field.get("default") is not None:
                    answers[field.get("question", "")] = field.get("default")
                elif field.get("type") == "mcq" and field.get("options"):
                    answers[field.get("question", "")] = field["options"][0]
            else:
                default = getattr(field, "default", None)
                if default is not None:
                    answers[getattr(field, "question", "")] = default
                elif getattr(field, "type", None) == "mcq" and getattr(field, "options", None):
                    answers[getattr(field, "question", "")] = getattr(field, "options")[0]
        answers = {k: v for k, v in answers.items() if k}
        return ClarificationResponse(
            request_id=request.request_id,
            answers=answers,
            skipped=True,
        )

    def _resolve_with_defaults(self, queued: QueuedClarification) -> None:
        if not queued.future.done():
            queued.future.set_result(self._default_response(queued.request))

    def _format_context(self, request: ClarificationRequest, answers: dict) -> str:
        lines = [f"\n[User clarification for task {request.task_id}:]"]
        if request.context:
            lines.append(f"Context: {request.context}")
        for field in request.fields:
            q = field.get("question") if isinstance(field, dict) else getattr(field, "question", "")
            if not q:
                continue
            a = answers.get(q, "(not answered)")
            lines.append(f"  - {q}: {a}")
        return "\n".join(lines)

