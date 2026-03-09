"""CLI for credential management: set, list, delete, migrate, export."""

import getpass
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from hivemind.credentials import (
    delete_credential,
    get_credential,
    list_credentials,
    set_credential,
)
from hivemind.credentials.migration import migrate_from_config

KNOWN_CREDENTIALS = {
    "openai": ["api_key"],
    "anthropic": ["api_key"],
    "github": ["token"],
    "gemini": ["api_key"],
    "azure": ["endpoint", "api_key", "deployment", "api_version"],
    "azure_anthropic": ["endpoint", "api_key", "deployment"],
}

# (provider, key) -> env var name for export
PROVIDER_KEY_TO_ENV: dict[tuple[str, str], str] = {
    ("openai", "api_key"): "OPENAI_API_KEY",
    ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    ("github", "token"): "GITHUB_TOKEN",
    ("gemini", "api_key"): "GEMINI_API_KEY",
    ("azure", "endpoint"): "AZURE_OPENAI_ENDPOINT",
    ("azure", "api_key"): "AZURE_OPENAI_API_KEY",
    ("azure", "deployment"): "AZURE_OPENAI_DEPLOYMENT_NAME",
    ("azure", "api_version"): "AZURE_OPENAI_API_VERSION",
    ("azure_anthropic", "endpoint"): "AZURE_ANTHROPIC_ENDPOINT",
    ("azure_anthropic", "api_key"): "AZURE_ANTHROPIC_API_KEY",
    ("azure_anthropic", "deployment"): "AZURE_ANTHROPIC_DEPLOYMENT_NAME",
}


def _env_escape(value: str) -> str:
    """Escape value for .env / export format: double-quote and escape internal quotes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _run_credentials_export(provider: str) -> int:
    """Print provider's credentials in env format (KEY=value, one per line)."""
    if provider not in KNOWN_CREDENTIALS:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return 1
    lines: list[str] = []
    for key in KNOWN_CREDENTIALS[provider]:
        env_var = PROVIDER_KEY_TO_ENV.get((provider, key))
        if not env_var:
            continue
        val = get_credential(provider, key)
        if val is not None:
            lines.append(f"{env_var}={_env_escape(val)}")
    if not lines:
        print(f"No credentials stored for provider: {provider}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def _run_credentials_set(provider: str, key: str) -> int:
    """Prompt for value and store credential."""
    if provider not in KNOWN_CREDENTIALS:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return 1
    if key not in KNOWN_CREDENTIALS[provider]:
        print(f"Unknown key for {provider}: {key}", file=sys.stderr)
        return 1
    try:
        value = getpass.getpass(f"Enter value for {provider}/{key}: ")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    if not value.strip():
        print("Empty value, not stored.", file=sys.stderr)
        return 1
    set_credential(provider, key, value.strip())
    print(f"Stored {provider}/{key}")
    return 0


def _run_credentials_list() -> int:
    """List credentials as table (provider, key). Never shows values."""
    creds = list_credentials()
    if not creds:
        print("No credentials stored.")
        return 0
    table = Table(title="Stored credentials")
    table.add_column("Provider", style="cyan")
    table.add_column("Key", style="green")
    for c in creds:
        table.add_row(c["provider"], c["key"])
    console = Console()
    console.print(table)
    return 0


def _run_credentials_delete(provider: str, key: str) -> int:
    """Remove a credential."""
    if provider not in KNOWN_CREDENTIALS:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return 1
    if key not in KNOWN_CREDENTIALS[provider]:
        print(f"Unknown key for {provider}: {key}", file=sys.stderr)
        return 1
    delete_credential(provider, key)
    print(f"Deleted {provider}/{key}")
    return 0


def _run_credentials_migrate() -> int:
    """Migrate credentials from TOML and env to store."""
    from hivemind.config.config_loader import project_config_paths

    config_path = None
    for p in project_config_paths():
        if p.is_file():
            config_path = p
            break
    if not config_path:
        config_path = Path.cwd() / "hivemind.toml"

    migrated = migrate_from_config(config_path)
    if not migrated:
        print("No credentials found in env or TOML to migrate.")
        return 0
    print(f"Migrated {len(migrated)} credential(s):")
    for item in migrated:
        print(f"  - {item}")
    print("\nYou can now remove these from hivemind.toml and .env for better security.")
    return 0


def run_credentials(args: object) -> int:
    """Dispatch credentials subcommand."""
    sub = getattr(args, "credentials_subcommand", None)
    provider = getattr(args, "provider", None)
    key = getattr(args, "key", None)

    if sub == "set":
        if not provider or not key:
            print("Usage: hivemind credentials set <provider> <key>", file=sys.stderr)
            return 1
        return _run_credentials_set(provider, key)
    if sub == "list":
        return _run_credentials_list()
    if sub == "delete":
        if not provider or not key:
            print("Usage: hivemind credentials delete <provider> <key>", file=sys.stderr)
            return 1
        return _run_credentials_delete(provider, key)
    if sub == "migrate":
        return _run_credentials_migrate()
    if sub == "export":
        if not provider:
            print("Usage: hivemind credentials export <provider>", file=sys.stderr)
            return 1
        return _run_credentials_export(provider)

    print("Usage: hivemind credentials set|list|delete|migrate|export", file=sys.stderr)
    return 1
