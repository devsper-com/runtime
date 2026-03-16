"""Migrate credentials from devsper.toml and env to the credential store."""

import os
from pathlib import Path

from devsper.credentials import set_credential


def _load_dotenv_for_config(config_path: Path) -> None:
    """Load .env from config directory so env vars are available for migration."""
    try:
        from dotenv import load_dotenv

        load_dotenv(config_path.parent / ".env")
    except Exception:
        pass

# Env var -> (provider, key)
_ENV_TO_CREDENTIAL: dict[str, tuple[str, str]] = {
    "OPENAI_API_KEY": ("openai", "api_key"),
    "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
    "GITHUB_TOKEN": ("github", "token"),
    "GEMINI_API_KEY": ("gemini", "api_key"),
    "GOOGLE_API_KEY": ("gemini", "api_key"),
    "AZURE_OPENAI_API_KEY": ("azure", "api_key"),
    "AZURE_OPENAI_ENDPOINT": ("azure", "endpoint"),
    "AZURE_OPENAI_DEPLOYMENT_NAME": ("azure", "deployment"),
    "AZURE_OPENAI_API_VERSION": ("azure", "api_version"),
    "AZURE_ANTHROPIC_ENDPOINT": ("azure_anthropic", "endpoint"),
    "AZURE_ANTHROPIC_API_KEY": ("azure_anthropic", "api_key"),
    "AZURE_ANTHROPIC_DEPLOYMENT_NAME": ("azure_anthropic", "deployment"),
}


def migrate_from_config(config_path: Path) -> list[str]:
    """
    Scan TOML and env for known credentials, migrate to store.
    Returns list of migrated items (e.g. ["openai/api_key", "azure/endpoint"]).
    Does NOT delete from env — inform user they can remove them.
    """
    migrated: list[str] = []

    # Load .env from config directory so all env vars are available
    _load_dotenv_for_config(config_path)

    # 1. Check env vars
    for env_var, (provider, key) in _ENV_TO_CREDENTIAL.items():
        val = os.environ.get(env_var)
        if val and str(val).strip():
            set_credential(provider, key, str(val).strip())
            migrated.append(f"{provider}/{key}")

    # 2. Check TOML
    if config_path.is_file():
        try:
            import tomllib

            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return migrated

        # [providers.azure]
        providers = data.get("providers") or {}
        azure = providers.get("azure")
        if isinstance(azure, dict):
            for toml_key, cred_key in [
                ("endpoint", "endpoint"),
                ("api_key", "api_key"),
                ("deployment", "deployment"),
                ("api_version", "api_version"),
            ]:
                val = azure.get(toml_key)
                if val is not None and str(val).strip():
                    item = f"azure/{cred_key}"
                    if item not in migrated:
                        set_credential("azure", cred_key, str(val).strip())
                        migrated.append(item)

        # Legacy sections: [openai], [anthropic], [azure_openai], etc.
        for section, (provider, key) in [
            ("openai", ("openai", "api_key")),
            ("anthropic", ("anthropic", "api_key")),
            ("google", ("gemini", "api_key")),
        ]:
            block = data.get(section)
            if isinstance(block, dict):
                val = block.get("api_key")
                if val is not None and str(val).strip():
                    item = f"{provider}/{key}"
                    if item not in migrated:
                        set_credential(provider, key, str(val).strip())
                        migrated.append(item)

        azure_block = data.get("azure_openai")
        if isinstance(azure_block, dict):
            for toml_key, cred_key in [
                ("endpoint", "endpoint"),
                ("api_key", "api_key"),
                ("deployment_name", "deployment"),
                ("api_version", "api_version"),
            ]:
                val = azure_block.get(toml_key)
                if val is not None and str(val).strip():
                    item = f"azure/{cred_key}"
                    if item not in migrated:
                        set_credential("azure", cred_key, str(val).strip())
                        migrated.append(item)

        azure_anthropic_block = data.get("azure_anthropic")
        if isinstance(azure_anthropic_block, dict):
            for toml_key, cred_key in [
                ("endpoint", "endpoint"),
                ("api_key", "api_key"),
                ("deployment_name", "deployment"),
            ]:
                val = azure_anthropic_block.get(toml_key)
                if val is not None and str(val).strip():
                    item = f"azure_anthropic/{cred_key}"
                    if item not in migrated:
                        set_credential("azure_anthropic", cred_key, str(val).strip())
                        migrated.append(item)

    return migrated
