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
    org_slug = (org or os.environ.get("DEVSPER_PLATFORM_ORG") or cs.get("platform", "org") or "").strip()
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


def cmd_cloud_login(args: Any) -> int:
    api_url = (getattr(args, "api_url", None) or "").strip().rstrip("/") or _default_api_url() or "http://localhost:8080"
    email = (getattr(args, "email", None) or "").strip()
    if not email:
        console.print("[red]--email is required.[/red]")
        return 1
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
        console.print(f"[red]Login failed[/red] HTTP {r.status_code}: {r.text[:500]}")
        return 1

    data = r.json()
    if data.get("mfa_required"):
        console.print("[red]This account has MFA enabled.[/red] Use a token from the web app or add MFA support to the CLI.")
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
        console.print("[red]No org slug available. Create an org via the API or pass --org.[/red]")
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

    console.print(f"[green]Logged in.[/green] api={api_url} org={org_slug}")
    return 0


def cmd_cloud_logout(_args: Any) -> int:
    cs = CredentialStore()
    for key in ("api_url", "org", "token", "refresh_token"):
        cs.delete("platform", key)
    for env in ("DEVSPER_PLATFORM_API_URL", "DEVSPER_PLATFORM_ORG", "DEVSPER_PLATFORM_TOKEN"):
        os.environ.pop(env, None)
    console.print("[dim]Cloud credentials cleared from keyring.[/dim]")
    return 0


def _load_json_file(path: str) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def _build_manifest_and_config(args: Any) -> tuple[dict[str, Any], dict[str, Any], str | None]:
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
            print(json.dumps({"run_id": run_id, "status": created.get("status", "pending")}))
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
        print(json.dumps({"run_id": run_id, "status": status, "raw": final}, default=str))
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
