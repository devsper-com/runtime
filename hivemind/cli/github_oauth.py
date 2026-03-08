"""
GitHub device flow for CLI login.

User opens https://github.com/login/device, enters the code shown in the terminal;
we open the browser, poll until they authorize, and return the access token to store.
"""

import time
import webbrowser
from typing import NamedTuple

import httpx

GITHUB_DEVICE_CLIENT_ID = "Ov23liXjWSSui6QIahPl"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# Default scopes for Copilot/Models API (repo for private repos; read:org optional)
DEFAULT_SCOPE = "read:user"


class DeviceFlowResult(NamedTuple):
    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class GitHubDeviceFlowError(Exception):
    pass


def request_device_code(
    client_id: str | None = None,
    scope: str = DEFAULT_SCOPE,
) -> DeviceFlowResult:
    """Request device and user codes from GitHub. Raises if client_id missing or request fails."""
    cid = (client_id or GITHUB_DEVICE_CLIENT_ID).strip()
    if not cid:
        raise GitHubDeviceFlowError(
            "GitHub device flow has no client_id configured; use token entry in the wizard instead."
        )
    with httpx.Client(timeout=15.0) as client:
        r = client.post(
            DEVICE_CODE_URL,
            headers={"Accept": "application/json"},
            data={"client_id": cid, "scope": scope},
        )
        r.raise_for_status()
        data = r.json()
    return DeviceFlowResult(
        user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        device_code=data["device_code"],
        interval=data.get("interval", 5),
        expires_in=data.get("expires_in", 900),
    )


def poll_access_token(
    device_code: str,
    client_id: str | None = None,
    interval: int = 5,
    timeout_seconds: int = 900,
) -> str:
    """
    Poll until the user authorizes the device; return access_token.
    Raises GitHubDeviceFlowError on expiry, access_denied, or other errors.
    """
    cid = (client_id or GITHUB_DEVICE_CLIENT_ID).strip()
    if not cid:
        raise GitHubDeviceFlowError("client_id required for polling; use token entry instead.")
    start = time.monotonic()
    while (time.monotonic() - start) < timeout_seconds:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                ACCESS_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": cid,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
        if r.status_code != 200:
            raise GitHubDeviceFlowError(f"Token request failed: {r.status_code} {r.text}")
        data = r.json()
        err = data.get("error")
        if err is None:
            token = data.get("access_token")
            if token:
                return token
            raise GitHubDeviceFlowError("No access_token in response")
        if err == "authorization_pending":
            time.sleep(interval)
            continue
        if err == "slow_down":
            interval = data.get("interval", interval + 5)
            time.sleep(interval)
            continue
        if err in ("expired_token", "token_expired"):
            raise GitHubDeviceFlowError("Device code expired. Please start login again.")
        if err == "access_denied":
            raise GitHubDeviceFlowError("Authorization was denied or cancelled.")
        raise GitHubDeviceFlowError(f"GitHub OAuth error: {err}")
    raise GitHubDeviceFlowError("Timed out waiting for authorization.")


def run_device_flow_cli(
    client_id: str | None = None,
    open_browser: bool = True,
) -> str:
    """
    Run device flow from the CLI: print code and URL, optionally open browser, poll for token.
    Returns the access token. Raises GitHubDeviceFlowError on failure.
    """
    result = request_device_code(client_id=client_id)
    verification_uri = result.verification_uri
    user_code = result.user_code

    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        console.print()
        console.print(
            Panel(
                f"[bold]Enter this code in your browser:[/] [cyan]{user_code}[/]\n\n"
                f"URL: [link={verification_uri}]{verification_uri}[/link]",
                title="GitHub device login",
                border_style="green",
            )
        )
        console.print()
    except Exception:
        print(f"\nEnter this code at {verification_uri}: {user_code}\n")

    if open_browser:
        try:
            webbrowser.open(verification_uri)
        except Exception:
            pass

    try:
        from rich.console import Console
        Console().print("[dim]Waiting for authorization…[/]")
    except Exception:
        print("Waiting for authorization…")

    return poll_access_token(
        result.device_code,
        client_id=client_id or GITHUB_DEVICE_CLIENT_ID,
        interval=result.interval,
        timeout_seconds=result.expires_in,
    )
