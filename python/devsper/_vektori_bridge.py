"""Vektori memory bridge — wraps vektori for Rust callbacks via PyO3."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class VektoriMemoryBridge:
    """
    Wraps a vektori.Vektori instance and exposes SYNCHRONOUS methods
    that Rust calls back into via PyO3.

    Thread safety: owns a dedicated event loop in a background daemon thread.
    All vektori async calls are dispatched via run_coroutine_threadsafe().
    """

    def __init__(
        self,
        database_url: str | None = None,
        storage_backend: str | None = None,
        embedding_model: str = "openai:text-embedding-3-small",
        extraction_model: str = "openai:gpt-4o-mini",
        embedding_dimension: int = 1536,
        agent_type: str = "general",
    ) -> None:
        # Create a dedicated event loop in a background thread.
        # This avoids conflicts with any existing asyncio loop (e.g., FastAPI).
        self._loop = asyncio.new_event_loop()
        self._shutdown = threading.Event()

        def _run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()

        # Initialize vektori on the background loop
        self._vektori = self._run_async(
            self._create_vektori(
                database_url=database_url,
                storage_backend=storage_backend,
                embedding_model=embedding_model,
                extraction_model=extraction_model,
                embedding_dimension=embedding_dimension,
                agent_type=agent_type,
            )
        )
        logger.info(
            "VektoriMemoryBridge initialized (backend=%s)", storage_backend or "sqlite"
        )

    async def _create_vektori(self, **kwargs):
        from vektori import Vektori  # Import here so it's optional

        v = Vektori(**kwargs)
        # Trigger lazy init so first real call isn't slow
        await v._ensure_initialized()
        return v

    def _run_async(self, coro):
        """Run an async coroutine on the background loop, blocking until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    # ── Methods called by Rust ──────────────────────────────────────

    def store(self, namespace: str, key: str, value: str) -> None:
        """
        Store a memory entry.
        namespace → user_id (isolated memory scope).
        key → used as part of session_id for dedup.
        value → the content to remember (JSON string).
        """
        try:
            session_id = f"devsper:{namespace}:{key}"
            messages = [{"role": "assistant", "content": value}]
            self._run_async(
                self._vektori.add(
                    messages=messages,
                    session_id=session_id,
                    user_id=namespace,
                )
            )
        except Exception:
            logger.exception(
                "VektoriMemoryBridge.store failed (ns=%s, key=%s)", namespace, key
            )

    def retrieve(self, namespace: str, key: str) -> str | None:
        """
        Retrieve a memory entry by key.
        Returns the content as a string, or None.
        """
        try:
            session_id = f"devsper:{namespace}:{key}"
            session = self._run_async(
                self._vektori.get_session(
                    session_id=session_id,
                    user_id=namespace,
                )
            )
            if session is None:
                return None
            # Return the session as JSON string
            return json.dumps(session)
        except Exception:
            logger.exception(
                "VektoriMemoryBridge.retrieve failed (ns=%s, key=%s)", namespace, key
            )
            return None

    def search(self, namespace: str, query: str, top_k: int) -> str:
        """
        Semantic search over memories.
        Returns JSON string of: [{"key": ..., "value": ..., "score": ...}]
        """
        try:
            result = self._run_async(
                self._vektori.search(
                    query=query,
                    user_id=namespace,
                    depth="l0",
                    top_k=top_k,
                )
            )
            # Convert vektori format to MemoryHit format
            hits = []
            for fact in result.get("facts", []):
                hits.append(
                    {
                        "key": fact.get("id", ""),
                        "value": {
                            "text": fact.get("text", ""),
                            "score": fact.get("score", 0.0),
                        },
                        "score": fact.get("score", 0.0),
                    }
                )
            return json.dumps(hits)
        except Exception:
            logger.exception("VektoriMemoryBridge.search failed (ns=%s)", namespace)
            return "[]"

    def delete(self, namespace: str, key: str) -> None:
        """Delete a memory entry. Best-effort."""
        try:
            if key == "__all__":
                self._run_async(self._vektori.delete_user(namespace))
            else:
                # vektori doesn't support single fact deletion from its public API
                # Best-effort: we just log. Full deletion via __all__.
                logger.warning(
                    "Single key deletion not supported by vektori public API (ns=%s, key=%s)",
                    namespace,
                    key,
                )
        except Exception:
            logger.exception(
                "VektoriMemoryBridge.delete failed (ns=%s, key=%s)", namespace, key
            )

    def health(self) -> str:
        """Returns health status as JSON."""
        return json.dumps({"status": "ok"})

    def close(self) -> None:
        """Shut down the background event loop and close vektori."""
        try:
            self._run_async(self._vektori.close())
        except Exception:
            logger.exception("VektoriMemoryBridge.close failed")
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop())
            self._thread.join(timeout=5)
