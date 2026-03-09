"""Credential store: OS keychain (keyring) only."""

import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "hivemind"

# Provider/key -> known keys for list_all
KNOWN_CREDENTIALS = {
    "openai": ["api_key"],
    "anthropic": ["api_key"],
    "github": ["token"],
    "gemini": ["api_key"],
    "azure": ["endpoint", "api_key", "deployment", "api_version"],
    "azure_anthropic": ["endpoint", "api_key", "deployment"],
}


def _username(provider: str, key: str) -> str:
    return f"{provider}/{key}"


class CredentialStore:
    """
    Secure credential store using OS keychain (keyring) only.
    Never logs credential values.
    """

    def get(self, provider: str, key: str) -> str | None:
        """Get credential from keyring. Returns None if not found or keyring unavailable."""
        username = _username(provider, key)
        try:
            import keyring
            from keyring.errors import KeyringError

            val = keyring.get_password(SERVICE_NAME, username)
            if val is not None:
                logger.debug("Credential %s/%s retrieved from keyring", provider, key)
            return val
        except KeyringError:
            logger.debug("Keyring unavailable")
            return None
        except Exception as e:
            logger.debug("Keyring error: %s", type(e).__name__)
            return None

    def set(self, provider: str, key: str, value: str) -> None:
        """Store credential in keyring."""
        username = _username(provider, key)
        try:
            import keyring
            from keyring.errors import KeyringError

            keyring.set_password(SERVICE_NAME, username, value)
            logger.debug("Credential %s/%s stored in keyring", provider, key)
        except KeyringError as e:
            raise RuntimeError("Keyring unavailable; cannot store credentials") from e
        except Exception as e:
            raise RuntimeError(f"Keyring error: {e}") from e

    def delete(self, provider: str, key: str) -> None:
        """Delete credential from keyring."""
        username = _username(provider, key)
        try:
            import keyring
            keyring.delete_password(SERVICE_NAME, username)
        except Exception:
            pass

    def list_all(self) -> list[dict]:
        """List stored credentials: [{provider, key, source}]. Never returns values."""
        result: list[dict] = []
        try:
            import keyring

            for provider, keys in KNOWN_CREDENTIALS.items():
                for k in keys:
                    username = _username(provider, k)
                    val = keyring.get_password(SERVICE_NAME, username)
                    if val is not None:
                        result.append({"provider": provider, "key": k, "source": "keyring"})
        except Exception:
            pass
        return result


_default_store: CredentialStore | None = None


def _get_store() -> CredentialStore:
    global _default_store
    if _default_store is None:
        _default_store = CredentialStore()
    return _default_store


def get_credential(provider: str, key: str) -> str | None:
    """Get credential from store. Returns None if not found."""
    return _get_store().get(provider, key)


def set_credential(provider: str, key: str, value: str) -> None:
    """Store credential in keyring."""
    _get_store().set(provider, key, value)


def delete_credential(provider: str, key: str) -> None:
    """Remove credential from store."""
    _get_store().delete(provider, key)


def list_credentials() -> list[dict]:
    """List stored credentials (provider, key, source). Never returns values."""
    return _get_store().list_all()
