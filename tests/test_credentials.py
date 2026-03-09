"""Tests for credential store (hivemind.credentials)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from hivemind.credentials import (
    delete_credential,
    get_credential,
    list_credentials,
    set_credential,
)
from hivemind.credentials.migration import migrate_from_config


def test_set_get_credential_roundtrip_mock_keyring():
    """set_credential / get_credential round-trip with mock keyring."""
    store: dict[str, str] = {}

    def mock_get(service: str, username: str) -> str | None:
        return store.get(username)

    def mock_set(service: str, username: str, password: str) -> None:
        store[username] = password

    def mock_delete(service: str, username: str) -> None:
        store.pop(username, None)

    with (
        patch("keyring.get_password", side_effect=mock_get),
        patch("keyring.set_password", side_effect=mock_set),
        patch("keyring.delete_password", side_effect=mock_delete),
    ):
        set_credential("openai", "api_key", "sk-test123")
        assert get_credential("openai", "api_key") == "sk-test123"
        delete_credential("openai", "api_key")
        assert get_credential("openai", "api_key") is None


def test_list_credentials_never_returns_values():
    """list_credentials returns only metadata, never values."""
    store: dict[str, str] = {}

    def mock_get(service: str, username: str) -> str | None:
        return store.get(username)

    def mock_set(service: str, username: str, password: str) -> None:
        store[username] = password

    with (
        patch("keyring.get_password", side_effect=mock_get),
        patch("keyring.set_password", side_effect=mock_set),
    ):
        set_credential("github", "token", "ghp_secret123")
        items = list_credentials()
        for item in items:
            assert "provider" in item
            assert "key" in item
            assert "value" not in item
            for k, v in item.items():
                assert "ghp_" not in str(v)
                assert "secret" not in str(v).lower()


def test_migrate_from_config_env(tmp_path):
    """migrate_from_config finds and stores env-based credentials in keyring."""
    config_path = tmp_path / "hivemind.toml"
    config_path.write_text("[swarm]\nworkers = 4\n")

    store: dict[str, str] = {}

    def mock_get(service: str, username: str) -> str | None:
        return store.get(username)

    def mock_set(service: str, username: str, password: str) -> None:
        store[username] = password

    with (
        patch("keyring.get_password", side_effect=mock_get),
        patch("keyring.set_password", side_effect=mock_set),
        patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-migrated",
                "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-5-mini",
                "AZURE_ANTHROPIC_ENDPOINT": "https://example.azure.com/anthropic/v1",
            },
        ),
    ):
        import hivemind.credentials.store as store_mod

        store_mod._default_store = None

        migrated = migrate_from_config(config_path)
        assert "openai/api_key" in migrated
        assert "azure/deployment" in migrated
        assert "azure_anthropic/endpoint" in migrated
        assert get_credential("openai", "api_key") == "sk-migrated"
        assert get_credential("azure", "deployment") == "gpt-5-mini"
        assert get_credential("azure_anthropic", "endpoint") == "https://example.azure.com/anthropic/v1"


def test_export_env_format(capsys):
    """credentials export prints KEY=value lines for provider."""
    store: dict[str, str] = {}

    def mock_get(service: str, username: str) -> str | None:
        return store.get(username)

    def mock_set(service: str, username: str, password: str) -> None:
        store[username] = password

    with (
        patch("keyring.get_password", side_effect=mock_get),
        patch("keyring.set_password", side_effect=mock_set),
    ):
        set_credential("openai", "api_key", "sk-export-test")
        from hivemind.credentials.cli import _run_credentials_export

        rc = _run_credentials_export("openai")
        assert rc == 0
        out = capsys.readouterr().out
        assert "OPENAI_API_KEY=" in out
        assert "sk-export-test" in out
