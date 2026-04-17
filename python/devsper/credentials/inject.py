"""Inject stored credentials as environment variables before Rust exec."""
from __future__ import annotations

import os

from devsper.credentials.providers import PROVIDERS
from devsper.credentials import store


def inject_credentials() -> None:
    """Read credentials from keyring, set missing env vars. Env vars take priority."""
    for provider in PROVIDERS.values():
        for field in provider.fields:
            if field.env_var and field.env_var not in os.environ:
                value = store.get(provider.name, field.name)
                if value is None and field.default is not None:
                    value = field.default
                if value:
                    os.environ[field.env_var] = value
