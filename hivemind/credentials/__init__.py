"""Secure credential store: OS keychain (keyring) only."""

from hivemind.credentials.store import (
    CredentialStore,
    delete_credential,
    get_credential,
    inject_into_env,
    list_credentials,
    set_credential,
)

__all__ = [
    "get_credential",
    "set_credential",
    "delete_credential",
    "list_credentials",
    "inject_into_env",
    "CredentialStore",
]
