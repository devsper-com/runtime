"""Keyring-backed credential store for Devsper providers."""
from __future__ import annotations

import keyring

from devsper.credentials.providers import PROVIDERS

_SERVICE = "devsper"


def _key(provider: str, field: str) -> str:
    return f"{provider}:{field}"


def set(provider: str, field: str, value: str) -> None:
    """Store a credential value in the system keyring."""
    keyring.set_password(_SERVICE, _key(provider, field), value)


def get(provider: str, field: str) -> str | None:
    """Retrieve a credential value from the system keyring. Returns None if not found."""
    return keyring.get_password(_SERVICE, _key(provider, field))


def delete(provider: str, field: str) -> None:
    """Remove a credential value from the system keyring."""
    try:
        keyring.delete_password(_SERVICE, _key(provider, field))
    except keyring.errors.PasswordDeleteError:
        pass


def list_configured() -> list[str]:
    """Return provider names that have at least one field stored in the keyring."""
    configured = []
    for provider_name, provider in PROVIDERS.items():
        for f in provider.fields:
            if keyring.get_password(_SERVICE, _key(provider_name, f.name)) is not None:
                configured.append(provider_name)
                break
    return configured
