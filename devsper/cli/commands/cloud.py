"""devsper cloud — login, run, status, logs against Devsper Platform API."""

from __future__ import annotations

import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

from devsper.credentials.store import CredentialStore
from devsper.platform.request_builder import PlatformAPIError, PlatformAPIRequestBuilder

console = Console()


def _default_api_url() -> str:
    return (
        os.environ.get("DEVSPER_PLATFORM_API_URL", "").strip().rstrip("/")
        or CredentialStore().get("platform", "api_url")
        or ""
    )


def _builder_from_args(
    api_url: str | None,
    org: str | None,
    token: str | None,
) -> PlatformAPIRequestBuilder:
    cs = CredentialStore()
    base = (api_url or _default_api_url() or "http://localhost:8080").rstrip("/")
    org_slug = (
        org or os.environ.get("DEVSPER_PLATFORM_ORG") or cs.get("platform", "org") or ""
    ).strip()
    tok = (
        token
        or os.environ.get("DEVSPER_PLATFORM_TOKEN")
        or cs.get("platform", "token")
        or ""
    ).strip()
    return PlatformAPIRequestBuilder(base_url=base, org_slug=org_slug, token=tok)


def _pick_org_slug(orgs: list[dict[str, Any]], explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    personal = [o for o in orgs if o.get("is_personal")]
    if personal:
        return str(personal[0].get("slug") or "")
    if orgs:
        return str(orgs[0].get("slug") or "")
    return ""


def _do_browser_login(api_url: str) -> dict[str, Any] | None:
    import http.server
    import socketserver
    import webbrowser
    import urllib.parse
    import json

    # We will run a local server
    class RequestHandler(http.server.SimpleHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            if self.path == "/callback":
                content_length = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(content_length)
                try:
                    data = json.loads(post_data.decode("utf-8"))
                    self.server.login_data = data
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(b'{"error":"bad_request"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), RequestHandler) as httpd:
        port = httpd.server_address[1]
        httpd.login_data = None

        # Open browser to the web app
        web_url = api_url.replace(":8080", ":5173")  # Hacky local replacement
        if "api." in web_url:
            web_url = web_url.replace("api.", "app.")

        login_url = f"{web_url}/cli-login?port={port}"

        from rich.panel import Panel
        from rich.align import Align

        console.print()
        console.print(
            Panel(
                f"Please authenticate in your browser.\n\n"
                f"[cyan underline]{login_url}[/]\n\n"
                "[dim]If your browser does not open automatically, click the link above.[/dim]",
                title="[bold blue]☁️ Devsper Cloud Login[/bold blue]",
                border_style="blue",
                expand=False,
            )
        )
        console.print()

        webbrowser.open(login_url)

        with console.status(
            "[bold cyan]Waiting for authentication in browser...[/bold cyan]",
            spinner="dots",
        ):
            # Wait for the callback (blocking)
            while httpd.login_data is None:
                httpd.handle_request()

        return httpd.login_data


def cmd_cloud_login(args: Any) -> int:
    api_url = (
        (getattr(args, "api_url", None) or "").strip().rstrip("/")
        or _default_api_url()
        or "http://localhost:8080"
    )
    email = (getattr(args, "email", None) or "").strip()

    access = ""
    refresh = ""

    if not email:
        # Browser login flow
        data = _do_browser_login(api_url)
        if not data or not data.get("token"):
            console.print("[red]Browser login failed or cancelled.[/red]")
            return 1
        access = data["token"]
        refresh = data.get("refresh_token", "")
    else:
        password = getattr(args, "password", None) or ""
        if not password:
            password = getpass.getpass("Password: ")

        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    f"{api_url}/auth/login",
                    json={"email": email, "password": password},
                    headers={"Content-Type": "application/json"},
                )
        except httpx.RequestError as e:
            console.print(f"[red]Could not reach platform API:[/red] {e}")
            return 1

        if r.status_code == 403:
            try:
                err = r.json().get("error", "")
            except Exception:
                err = ""
            if err == "email_not_verified":
                console.print(
                    "[yellow]Email not verified.[/yellow] Open Mailhog at http://localhost:8025 (local compose) "
                    "and complete verification, or set EMAIL_VERIFICATION_ENABLED=false for local dev."
                )
                return 1
        if r.status_code != 200:
            console.print(
                f"[red]Login failed[/red] HTTP {r.status_code}: {r.text[:500]}"
            )
            return 1

        data = r.json()
        if data.get("mfa_required"):
            console.print(
                "[red]This account has MFA enabled.[/red] Use a token from the web app or add MFA support to the CLI."
            )
            return 1

        access = (data.get("access_token") or "").strip()
        refresh = (data.get("refresh_token") or "").strip()
        if not access:
            console.print("[red]No access_token in response.[/red]")
            return 1

    try:
        with httpx.Client(timeout=60.0) as client:
            me = client.get(
                f"{api_url}/me",
                headers={"Authorization": f"Bearer {access}"},
            )
    except httpx.RequestError as e:
        console.print(f"[red]Could not fetch /me:[/red] {e}")
        return 1

    if me.status_code != 200:
        console.print(f"[red]/me failed[/red] HTTP {me.status_code}: {me.text[:500]}")
        return 1

    me_body = me.json()
    orgs = me_body.get("orgs") or []
    if not isinstance(orgs, list):
        orgs = []
    org_slug = _pick_org_slug(orgs, getattr(args, "org", None))
    if not org_slug:
        console.print(
            "[red]No org slug available. Create an org via the API or pass --org.[/red]"
        )
        return 1

    cs = CredentialStore()
    try:
        cs.set("platform", "api_url", api_url)
        cs.set("platform", "org", org_slug)
        cs.set("platform", "token", access)
        if refresh:
            cs.set("platform", "refresh_token", refresh)
    except RuntimeError as e:
        console.print(f"[red]Could not store credentials:[/red] {e}")
        return 1

    os.environ["DEVSPER_PLATFORM_API_URL"] = api_url
    os.environ["DEVSPER_PLATFORM_ORG"] = org_slug
    os.environ["DEVSPER_PLATFORM_TOKEN"] = access

    from rich.panel import Panel

    console.print()
    user_email = me_body.get("email") or me_body.get("name") or "User"
    console.print(
        Panel(
            f"Successfully authenticated as [bold cyan]{user_email}[/bold cyan]!\n\n"
            f"[dim]API URL:[/dim] {api_url}\n"
            f"[dim]Organization:[/dim] [bold green]{org_slug}[/bold green]",
            title="[bold green]✅ Login Complete[/bold green]",
            border_style="green",
            expand=False,
        )
    )
    console.print()
    return 0


def cmd_cloud_logout(_args: Any) -> int:
    cs = CredentialStore()
    for key in ("api_url", "org", "token", "refresh_token"):
        cs.delete("platform", key)
    for env in (
        "DEVSPER_PLATFORM_API_URL",
        "DEVSPER_PLATFORM_ORG",
        "DEVSPER_PLATFORM_TOKEN",
    ):
        os.environ.pop(env, None)

    from rich.panel import Panel

    console.print()
    console.print(
        Panel(
            "You have been successfully logged out.\n\n"
            "[dim]Cloud credentials cleared from keychain.[/dim]",
            title="[bold yellow]👋 Logged Out[/bold yellow]",
            border_style="yellow",
            expand=False,
        )
    )
    console.print()
    return 0


def _load_json_file(path: str) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _build_manifest_and_config(
    args: Any,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    manifest: dict[str, Any] = {}
    config: dict[str, Any] = {}
    manifest_version: str | None = None

    mf = (getattr(args, "manifest", None) or "").strip()
    if mf:
        manifest = dict(_load_json_file(mf))

    wf_name = (getattr(args, "workflow", None) or "").strip()
    if wf_name:
        from devsper.workflow.loader import load_workflow

        wf = load_workflow(wf_name)
        if wf is None:
            raise ValueError(f"Workflow not found: {wf_name}")
        manifest["devsper_workflow"] = wf.model_dump(mode="json")

    cfg_path = (getattr(args, "config", None) or "").strip()
    if cfg_path:
        config = dict(_load_json_file(cfg_path))

    mv = getattr(args, "manifest_version", None)
    if mv and str(mv).strip():
        manifest_version = str(mv).strip()

    return manifest, config, manifest_version


def cmd_cloud_import_keys(args: Any) -> int:
    from devsper.credentials import list_credentials, get_credential

    api = _builder_from_args(
        getattr(args, "api_url", None),
        getattr(args, "org", None),
        getattr(args, "token", None),
    )
    if not api.enabled():
        console.print(
            "[red]Platform not configured.[/red] Run [bold]devsper cloud login[/bold] or set "
            "DEVSPER_PLATFORM_API_URL + DEVSPER_PLATFORM_ORG + DEVSPER_PLATFORM_TOKEN."
        )
        return 1

    if not api.org_slug:
        console.print(
            "[red]No org specified.[/red] Run login again or set DEVSPER_PLATFORM_ORG."
        )
        return 1

    creds = list_credentials()
    if not creds:
        console.print(
            "No local credentials found. Use [bold]devsper credentials set[/bold] first."
        )
        return 0

    target_provider = getattr(args, "provider", None)
    if target_provider:
        target_provider = target_provider.strip().lower()

    success_count = 0
    from rich.panel import Panel

    console.print(
        f"Importing local credentials to platform org: [bold cyan]{api.org_slug}[/bold cyan]\n"
    )

    for c in creds:
        provider = c["provider"]
        key = c["key"]

        if target_provider and provider != target_provider:
            continue

        if key not in ("api_key", "token"):
            # Only push the main API key / token to the platform for now
            continue

        val = get_credential(provider, key)
        if not val:
            continue

        try:
            # The platform API expects PUT /orgs/{slug}/provider-keys/{provider} with {"key": val}
            api.request(
                "PUT",
                f"/orgs/{api.org_slug}/provider-keys/{provider}",
                json_body={"key": val},
            )
            console.print(f"✅ [green]Successfully imported {provider} ({key})[/green]")
            success_count += 1
        except Exception as e:
            console.print(f"❌ [red]Failed to import {provider}: {e}[/red]")

    if success_count > 0:
        console.print()
        console.print(
            Panel(
                f"Successfully synced {success_count} provider key(s) to Devsper Cloud.\n"
                "Your backend workers can now use these keys for LLM completions.",
                title="[bold green]Import Complete[/bold green]",
                expand=False,
            )
        )
    else:
        if target_provider:
            console.print(
                f"No suitable credentials found for provider '{target_provider}'."
            )
        else:
            console.print("No supported provider keys found to import.")
    return 0


def cmd_cloud_run(args: Any) -> int:
    task = (getattr(args, "task", None) or "").strip()
    if not task:
        console.print("[red]Task text is required.[/red]")
        return 1

    api = _builder_from_args(
        getattr(args, "api_url", None),
        getattr(args, "org", None),
        getattr(args, "token", None),
    )
    if not api.enabled():
        console.print(
            "[red]Platform not configured.[/red] Run [bold]devsper cloud login[/bold] or set "
            "DEVSPER_PLATFORM_API_URL + DEVSPER_PLATFORM_ORG + DEVSPER_PLATFORM_TOKEN."
        )
        return 1

    try:
        manifest, config, manifest_version = _build_manifest_and_config(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        console.print(f"[red]{e}[/red]")
        return 1

    project_id = (getattr(args, "project_id", None) or "").strip() or None
    timeout_poll = float(getattr(args, "timeout", 300.0))
    no_wait = bool(getattr(args, "no_wait", False))
    json_out = bool(getattr(args, "json_output", False))

    try:
        created = api.create_run(
            task=task,
            project_id=project_id or "",
            config=config,
            manifest=manifest,
            manifest_version=manifest_version,
        )
    except PlatformAPIError as e:
        console.print(f"[red]create_run failed:[/red] {e}")
        if getattr(e, "body", None):
            console.print(str(e.body))
        return 1

    run_id = str(created.get("run_id") or created.get("id") or "")
    if not run_id:
        console.print(f"[red]Unexpected create response:[/red] {created!r}")
        return 1

    if no_wait:
        if json_out:
            print(
                json.dumps(
                    {"run_id": run_id, "status": created.get("status", "pending")}
                )
            )
        else:
            console.print(f"[green]Queued[/green] run_id={run_id}")
        return 0

    try:
        final = api.poll_run(
            run_id,
            interval_seconds=float(getattr(args, "interval", 2.0)),
            timeout_seconds=timeout_poll,
            terminal_statuses=("completed", "failed", "cancelled", "timeout"),
        )
    except TimeoutError as e:
        console.print(f"[yellow]{e}[/yellow]")
        return 1
    except PlatformAPIError as e:
        console.print(f"[red]poll failed:[/red] {e}")
        return 1

    status = str(final.get("status") or "")
    if json_out:
        print(
            json.dumps({"run_id": run_id, "status": status, "raw": final}, default=str)
        )
    else:
        console.print(f"run_id={run_id} status={status}")
        result = final.get("result")
        if result is not None:
            console.print(json.dumps(result, indent=2, default=str))

    return 0 if status == "completed" else 1


def cmd_cloud_status(args: Any) -> int:
    run_id = (getattr(args, "run_id", None) or "").strip()
    if not run_id:
        console.print("[red]run_id required.[/red]")
        return 1

    api = _builder_from_args(
        getattr(args, "api_url", None),
        getattr(args, "org", None),
        getattr(args, "token", None),
    )
    if not api.enabled():
        console.print("[red]Platform not configured.[/red]")
        return 1

    try:
        data = api.get_json(f"/orgs/{api.org_slug}/runs/{run_id}")
    except PlatformAPIError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    if bool(getattr(args, "json_output", False)):
        print(json.dumps(data, indent=2, default=str))
        return 0

    status = data.get("status", "")
    console.print(f"run_id={run_id} status={status}")
    if data.get("result") is not None:
        console.print(json.dumps(data.get("result"), indent=2, default=str))
    return 0


def cmd_cloud_logs(args: Any) -> int:
    run_id = (getattr(args, "run_id", None) or "").strip()
    if not run_id:
        console.print("[red]run_id required.[/red]")
        return 1

    api = _builder_from_args(
        getattr(args, "api_url", None),
        getattr(args, "org", None),
        getattr(args, "token", None),
    )
    if not api.enabled():
        console.print("[red]Platform not configured.[/red]")
        return 1

    try:
        data = api.get_json(f"/orgs/{api.org_slug}/runs/{run_id}/events")
    except PlatformAPIError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    events = data.get("events") or []
    if bool(getattr(args, "json_output", False)):
        print(json.dumps(data, indent=2, default=str))
        return 0

    if not events:
        console.print("[dim]No events.[/dim]")
        return 0

    table = Table(show_header=True, header_style="bold")
    table.add_column("event_type")
    table.add_column("payload", max_width=72)
    for ev in events:
        et = str(ev.get("event_type", ""))
        payload = ev.get("payload")
        if isinstance(payload, (dict, list)):
            ps = json.dumps(payload, default=str)[:500]
        else:
            ps = str(payload)[:500]
        table.add_row(et, ps)
    console.print(table)
    return 0
