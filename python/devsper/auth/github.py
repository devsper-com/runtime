"""GitHub device flow authentication."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

import click
from rich.console import Console
from rich.panel import Panel

CLIENT_ID_ENV = "DEVSPER_GITHUB_CLIENT_ID"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPE = "read:user"
TIMEOUT_SECONDS = 900  # 15 minutes

console = Console()


def _post_json(url: str, data: dict) -> dict:
    """POST URL-encoded data, return JSON response."""
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def login() -> str:
    """Run GitHub device flow, return access token.

    Raises:
        click.ClickException: if CLIENT_ID_ENV is not set or flow fails.
    """
    client_id = os.environ.get(CLIENT_ID_ENV)
    if not client_id:
        raise click.ClickException(
            f"{CLIENT_ID_ENV} not set.\n"
            "Register a GitHub OAuth App at https://github.com/settings/developers\n"
            f"then set: export {CLIENT_ID_ENV}=<your-client-id>"
        )

    # Request device + user codes
    device_data = _post_json(DEVICE_CODE_URL, {"client_id": client_id, "scope": SCOPE})

    user_code: str = device_data["user_code"]
    verification_uri: str = device_data["verification_uri"]
    device_code: str = device_data["device_code"]
    interval: int = int(device_data.get("interval", 5))
    expires_in: int = int(device_data.get("expires_in", TIMEOUT_SECONDS))

    console.print(
        Panel(
            f"[bold]Open this URL in your browser:[/bold]\n\n"
            f"  [cyan]{verification_uri}[/cyan]\n\n"
            f"[bold]Enter this code:[/bold]\n\n"
            f"  [bold yellow]{user_code}[/bold yellow]",
            title="GitHub Login",
            expand=False,
        )
    )

    deadline = time.monotonic() + expires_in
    with console.status("[dim]Waiting for GitHub authorization...[/dim]"):
        while time.monotonic() < deadline:
            time.sleep(interval)
            token_data = _post_json(
                TOKEN_URL,
                {
                    "client_id": client_id,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )

            error = token_data.get("error")
            if error == "authorization_pending":
                continue
            elif error == "slow_down":
                interval += 5
                continue
            elif error == "expired_token":
                raise click.ClickException("Device code expired. Run the command again.")
            elif error == "access_denied":
                raise click.ClickException("Authorization was denied.")
            elif error:
                raise click.ClickException(f"GitHub authorization error: {error}")

            access_token = token_data.get("access_token")
            if access_token:
                return access_token

    raise click.ClickException("Timed out waiting for GitHub authorization. Run the command again.")
