"""Shared HTTP client and token helpers for the Hivemind package registry."""

import os

import httpx

REGISTRY_URL = os.environ.get(
    "HIVEMIND_REGISTRY_URL",
    "https://registry.hivemind.rithul.dev",
)

CREDENTIAL_SERVICE = "hivemind_registry"
CREDENTIAL_USERNAME = "api_key"


def get_token() -> str | None:
    """Read stored API key from OS keychain, falling back to env var."""
    try:
        from hivemind.credentials import get_credential

        token = get_credential(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME)
        if token:
            return token
    except Exception:
        pass
    return os.environ.get("HIVEMIND_API_KEY")


def set_token(token: str) -> None:
    """Store API key in OS keychain."""
    from hivemind.credentials import set_credential

    set_credential(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME, token)


def delete_token() -> None:
    """Remove API key from OS keychain."""
    try:
        from hivemind.credentials import delete_credential

        delete_credential(CREDENTIAL_SERVICE, CREDENTIAL_USERNAME)
    except Exception:
        pass


def require_token() -> str:
    """Get token or exit with helpful message."""
    token = get_token()
    if not token:
        from rich.console import Console

        Console().print(
            "[red]Not logged in.[/red] Run [bold]hivemind reg login[/bold] first.\n"
            "Or set [bold]HIVEMIND_API_KEY[/bold] env var for CI."
        )
        raise SystemExit(1)
    return token


class RegistryClient:
    """Thin HTTP wrapper for the Hivemind package registry API."""

    def __init__(self, token: str | None = None):
        self.base = REGISTRY_URL.rstrip("/")
        self.token = token
        self._client = httpx.Client(timeout=30)

    def _headers(self) -> dict:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["X-API-Key"] = self.token
        return h

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._client.get(f"{self.base}{path}", headers=self._headers(), **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self._client.post(
            f"{self.base}{path}", headers=self._headers(), **kwargs
        )

    def close(self) -> None:
        self._client.close()
