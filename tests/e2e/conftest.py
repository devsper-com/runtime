"""
E2E test fixtures for Ollama at 192.168.1.2.

Run with:
    OLLAMA_HOST=http://192.168.1.2:11434 uv run pytest tests/e2e/ -v -s

Tests are skipped automatically if the Ollama server is unreachable.
"""
import os
import pytest
import httpx

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.2:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")


def ollama_available() -> bool:
    """Return True if Ollama server is reachable and the model is present."""
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        if r.status_code != 200:
            return False
        tags = [m.get("name", "") for m in r.json().get("models", [])]
        # Accept exact match or family prefix match
        family = OLLAMA_MODEL.split(":")[0]
        return any(t == OLLAMA_MODEL or t.startswith(family) for t in tags)
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not ollama_available(),
    reason=f"Ollama not reachable at {OLLAMA_HOST} or model {OLLAMA_MODEL} not loaded",
)


@pytest.fixture(autouse=True)
def set_ollama_env(monkeypatch):
    """Point all model calls at the remote Ollama instance and reset router cache."""
    monkeypatch.setenv("OLLAMA_HOST", OLLAMA_HOST)
    monkeypatch.setenv("DEVSPER_MID_MODEL", OLLAMA_MODEL)
    monkeypatch.setenv("DEVSPER_FAST_MODEL", OLLAMA_MODEL)
    monkeypatch.setenv("DEVSPER_SLOW_MODEL", OLLAMA_MODEL)
    # Reset the cached LLM router so it picks up the new OLLAMA_HOST
    try:
        import devsper.providers.router.factory as _factory
        monkeypatch.setattr(_factory, "_router_instance", None)
    except Exception:
        pass
