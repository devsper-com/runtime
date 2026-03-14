"""hivemind reg — registry CLI commands.

Subcommands: login, logout, whoami, test, publish, search, info, versions, yank.
"""

import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from hivemind.plugins.registry import (
    REGISTRY_URL,
    RegistryClient,
    delete_token,
    get_token,
    require_token,
    set_token,
)

console = Console()

SPINNER_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]


# ── login ──────────────────────────────────────────────────────────────────


def cmd_login(args):
    """Device-flow login: open browser to approve, CLI polls until done."""
    client = RegistryClient()

    # 1. Request device code
    try:
        r = client.post("/api/v1/auth/device/request", json={})
        r.raise_for_status()
    except Exception as e:
        console.print(f"[red]Could not reach registry:[/red] {e}")
        raise SystemExit(1)

    data = r.json()
    device_code = data["device_code"]
    user_code = data["user_code"]
    verify_uri = data["verification_uri"]
    expires_in = data.get("expires_in", 300)
    poll_interval = data.get("interval", 5)

    # 2. Display instructions
    console.print(
        Panel(
            f"[bold]Open:[/bold]  {verify_uri}\n"
            f"[bold]Code:[/bold]  [yellow]{user_code}[/yellow]\n\n"
            "Waiting for you to approve in the browser...",
            title="[bold]hivemind registry login[/bold]",
            border_style="dim",
        )
    )

    # 3. Poll for authorization
    deadline = time.time() + expires_in
    frame_i = 0

    with Live(console=console, refresh_per_second=8) as live:
        while time.time() < deadline:
            remaining = int(deadline - time.time())
            live.update(
                f"  {SPINNER_FRAMES[frame_i % len(SPINNER_FRAMES)]}  "
                f"[dim]Waiting for authorization ({remaining}s remaining)...[/dim]"
            )
            frame_i += 1
            time.sleep(poll_interval)

            try:
                pr = client.post(
                    "/api/v1/auth/device/poll",
                    json={"device_code": device_code},
                )
            except Exception:
                continue  # network blip — keep trying

            if pr.status_code == 200:
                token = pr.json().get("token")
                if token:
                    live.stop()
                    set_token(token)
                    console.print(
                        "\n[green]✓ Logged in.[/green] "
                        "Token stored in OS keychain.\n"
                        "Run [bold]hivemind reg whoami[/bold] to verify."
                    )
                    return 0

            elif pr.status_code == 400:
                live.stop()
                console.print("\n[red]✗ Authorization denied.[/red]")
                raise SystemExit(1)

            elif pr.status_code == 410:
                live.stop()
                console.print(
                    "\n[red]✗ Code expired.[/red] "
                    "Run [bold]hivemind reg login[/bold] again."
                )
                raise SystemExit(1)

            # 202 = still pending — keep looping

    console.print("\n[red]✗ Timed out waiting for authorization.[/red]")
    raise SystemExit(1)


# ── logout ─────────────────────────────────────────────────────────────────


def cmd_logout(args):
    delete_token()
    console.print("[green]✓ Logged out.[/green]")
    return 0


# ── whoami ─────────────────────────────────────────────────────────────────


def cmd_whoami(args):
    token = require_token()
    client = RegistryClient(token)
    try:
        r = client.get("/api/v1/me")
    except Exception as e:
        console.print(f"[red]Error contacting registry:[/red] {e}")
        return 1

    if r.status_code == 401:
        console.print(
            "[red]Token invalid or expired.[/red] "
            "Run [bold]hivemind reg login[/bold] again."
        )
        raise SystemExit(1)
    r.raise_for_status()

    d = r.json()
    masked = token[:6] + "••••••••••••" + token[-4:]
    username = d.get("username") or d.get("email") or d.get("id") or "—"
    console.print(f"[bold]Username:[/bold]  {username}")
    if d.get("email"):
        console.print(f"[bold]Email:[/bold]     {d['email']}")
    console.print(f"[bold]ID:[/bold]        {d.get('id', '—')}")
    console.print(f"[bold]API key:[/bold]   {masked}")
    return 0


# ── test ───────────────────────────────────────────────────────────────────


def cmd_test(args):
    """Validate that the directory is a publishable hivemind plugin."""
    directory = getattr(args, "dir", ".")
    path = Path(directory).resolve()
    passed = 0
    failed = 0

    def check(desc: str, ok: bool, warn: bool = False):
        nonlocal passed, failed
        if ok:
            console.print(f"  [green]✓[/green] {desc}")
            passed += 1
        elif warn:
            console.print(f"  [yellow]⚠[/yellow]  {desc} [dim](warning)[/dim]")
        else:
            console.print(f"  [red]✗[/red] {desc}")
            failed += 1

    console.print(f"\n[bold]Validating plugin:[/bold] {path}\n")

    # pyproject.toml
    pyproject_path = path / "pyproject.toml"
    has_pyproject = pyproject_path.exists()
    check("pyproject.toml exists", has_pyproject)
    if not has_pyproject:
        console.print("\n[red]Cannot continue without pyproject.toml[/red]")
        raise SystemExit(1)

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    project = pyproject.get("project", {})
    eps = project.get("entry-points", {})
    plugin_eps = eps.get("hivemind.plugins", {})

    check('[project.entry-points."hivemind.plugins"] present', bool(plugin_eps))
    check("version field present", bool(project.get("version")))
    check("description field present", bool(project.get("description")))
    check("license field present", bool(project.get("license")))

    requires_python = project.get("requires-python", "")
    # Accept any constraint that allows 3.12+ (e.g. ">=3.10", ">=3.12", ">=3.13")
    rp_ok = False
    if requires_python:
        import re

        # Extract version numbers from the constraint
        versions = re.findall(r"(\d+)\.(\d+)", requires_python)
        for major, minor in versions:
            if int(major) == 3 and int(minor) <= 12:
                rp_ok = True
                break
            if int(major) == 3 and int(minor) > 12:
                # e.g. >=3.13 also fine
                rp_ok = True
                break
    check("requires-python allows 3.12+", rp_ok)

    # requires-hivemind (custom metadata — warn only)
    raw_text = pyproject_path.read_text()
    check("requires-hivemind field present", "requires-hivemind" in raw_text, warn=True)

    # Entry point loads
    if plugin_eps:
        ep_value = list(plugin_eps.values())[0]
        module_path, _, func = ep_value.partition(":")
        func = func or "register"
        # Test that the entry point loads and returns a list (or None)
        load_script = (
            f"import sys; sys.path.insert(0,'.'); "
            f"from {module_path} import {func}; result = {func}(); "
            f"r = result if result is not None else []; "
            f"assert isinstance(r, list), 'must return list or None'; "
            f"tool_objs = [t for t in r if hasattr(t,'name') and hasattr(t,'run')]; "
            f"str_names = [t for t in r if isinstance(t, str)]; "
            f"none_flag = '1' if result is None else '0'; "
            f"print(f'{{len(tool_objs)}}:{{len(str_names)}}:{{none_flag}}')"
        )
        result = subprocess.run(
            [sys.executable, "-c", load_script],
            capture_output=True,
            text=True,
            cwd=path,
        )
        loads_ok = result.returncode == 0
        check("Entry point loads without error", loads_ok)
        if loads_ok:
            output = result.stdout.strip()
            parts = output.split(":")
            tool_obj_count = int(parts[0]) if parts[0] else 0
            str_name_count = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            is_none = parts[2] == "1" if len(parts) > 2 else False
            total_items = tool_obj_count + str_name_count

            if is_none and total_items == 0:
                check("Entry point returns (self-registers, returns None)", True)
            else:
                check(
                    f"Entry point returns {total_items} item(s) "
                    f"({tool_obj_count} Tool object(s), {str_name_count} name(s))",
                    total_items > 0,
                )
                # Validate Tool objects have required attributes
                if tool_obj_count > 0:
                    validate = subprocess.run(
                        [
                            sys.executable,
                            "-c",
                            f"import sys; sys.path.insert(0,'.'); "
                            f"from {module_path} import {func}; result = {func}(); "
                            f"tools = [t for t in result if hasattr(t,'name') and hasattr(t,'run')]; "
                            f"assert all(hasattr(t,'name') and hasattr(t,'description') "
                            f"and hasattr(t,'run') for t in tools), "
                            f"'Tool missing required attribute'; "
                            f"print('ok')",
                        ],
                        capture_output=True,
                        text=True,
                        cwd=path,
                    )
                    check(
                        "Each Tool object has name, description, run()",
                        validate.returncode == 0,
                    )
        else:
            console.print(f"    [dim]{result.stderr.strip()}[/dim]")
    else:
        check("Entry point loads without error", False)

    console.print()
    total = passed + failed
    if failed == 0:
        console.print(
            f"[green]✓ {passed}/{total} checks passed.[/green] "
            "Plugin is ready to publish.\n"
            "Run [bold]hivemind reg publish[/bold] to publish."
        )
    else:
        console.print(
            f"[red]✗ {failed} check(s) failed.[/red] {passed}/{total} passed."
        )
        raise SystemExit(1)
    return 0


# ── publish ────────────────────────────────────────────────────────────────


def _read_pyproject(path: Path) -> dict:
    """Read and return parsed pyproject.toml from the given directory."""
    pyproject_path = path / "pyproject.toml"
    if not pyproject_path.exists():
        return {}
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)


def _ensure_package_exists(client: RegistryClient, name: str, meta: dict) -> None:
    """Check if package exists on registry; if not, create it from pyproject metadata."""
    r = client.get(f"/api/v1/packages/{name}")
    if r.status_code == 200:
        return  # already exists

    if r.status_code != 404:
        # Unexpected error
        console.print(f"[red]Error checking package ({r.status_code}):[/red] {r.text}")
        raise SystemExit(1)

    # Package doesn't exist — create it
    project = meta.get("project", {})
    description = project.get("description", "")
    license_val = project.get("license", "")
    # license can be a string or a dict like {text: "MIT"}
    if isinstance(license_val, dict):
        license_val = license_val.get("text", license_val.get("file", ""))
    homepage = ""
    repository = ""
    urls = project.get("urls", {})
    if urls:
        homepage = urls.get("Homepage", urls.get("homepage", ""))
        repository = urls.get(
            "Repository",
            urls.get("repository", urls.get("Source", urls.get("source", ""))),
        )
    keywords = project.get("keywords", [])

    console.print(
        f"\n[yellow]Package '{name}' does not exist on the registry.[/yellow]\n"
        f"  Creating it from pyproject.toml metadata..."
    )

    cr = client.post(
        "/api/v1/packages",
        json={
            "Name": name,
            "DisplayName": project.get("name", name),
            "Description": description,
            "Homepage": homepage or "",
            "Repository": repository or "",
            "License": license_val,
            "Keywords": keywords,
        },
    )

    if cr.status_code == 201:
        console.print(f"  [green]✓ Package '{name}' created.[/green]\n")
    elif cr.status_code == 409:
        # Race condition or namespace mismatch — package exists now
        console.print(f"  [dim]Package '{name}' already exists.[/dim]\n")
    else:
        console.print(
            f"  [red]Failed to create package ({cr.status_code}):[/red] {cr.text}\n"
            f"  You can create it manually at {REGISTRY_URL} or via:\n"
            f"    curl -X POST {REGISTRY_URL}/api/v1/packages \\\n"
            f"      -H 'X-API-Key: <token>' \\\n"
            f"      -H 'Content-Type: application/json' \\\n"
            f'      -d \'{{"Name": "{name}"}}\''
        )
        raise SystemExit(1)


def cmd_publish(args):
    directory = getattr(args, "dir", ".")
    skip_build = getattr(args, "skip_build", False)
    dry_run = getattr(args, "dry_run", False)
    path = Path(directory).resolve()
    token = require_token()

    # Read pyproject.toml for metadata
    meta = _read_pyproject(path)
    project = meta.get("project", {})

    # Validate first
    console.print("[dim]Running plugin validation...[/dim]")
    try:
        cmd_test(args)
    except SystemExit as e:
        if e.code and e.code != 0:
            raise

    # Build
    if not skip_build:
        console.print("\n[bold]Building...[/bold]")
        import shutil

        # Clean dist directory to avoid uploading stale files
        dist_dir = path / "dist"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)

        # Try python -m build first, fall back to uv build
        result = subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(path / "dist")],
            cwd=path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Fall back to uv build if available
            uv_bin = shutil.which("uv")
            if uv_bin:
                console.print(
                    "[dim]python -m build unavailable, falling back to uv build...[/dim]"
                )
                result = subprocess.run(
                    [uv_bin, "build", "--out-dir", str(path / "dist")],
                    cwd=path,
                )
                if result.returncode != 0:
                    console.print("[red]Build failed.[/red]")
                    raise SystemExit(1)
            else:
                console.print(
                    f"[red]Build failed.[/red]\n"
                    f"[dim]{result.stderr.strip()}[/dim]\n"
                    "Install the build package: [bold]pip install build[/bold] "
                    "or use [bold]uv build[/bold]."
                )
                raise SystemExit(1)

    dist = path / "dist"
    files = sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz"))
    if not files:
        console.print(
            "[red]No dist files found.[/red] "
            "Run without --skip-build or run `python -m build` first."
        )
        raise SystemExit(1)

    # Determine canonical package name + version from pyproject.toml
    # (more reliable than parsing filenames)
    pkg_name = project.get("name", "").lower().replace("_", "-")
    pkg_version = project.get("version", "")

    # Fallback: parse from first wheel filename if pyproject metadata missing
    if not pkg_name or not pkg_version:
        stem = files[0].stem
        parts = stem.split("-")
        if not pkg_name:
            pkg_name = parts[0].replace("_", "-").lower()
        if not pkg_version and len(parts) > 1:
            pkg_version = parts[1]

    if dry_run:
        console.print(
            f"\n[bold]Dry run — would upload as {pkg_name}@{pkg_version}:[/bold]"
        )
        for f in files:
            console.print(f"  {f.name}")
        return 0

    client = RegistryClient(token)

    # Ensure package exists on registry (auto-create if needed)
    _ensure_package_exists(client, pkg_name, meta)

    for file in files:
        console.print(f"\n[bold]Uploading[/bold] {file.name}...")

        with open(file, "rb") as fh:
            try:
                r = httpx.post(
                    f"{REGISTRY_URL}/api/v1/packages/{pkg_name}/upload",
                    headers={"X-API-Key": token},
                    files={"file": (file.name, fh, "application/octet-stream")},
                    data={
                        "name": pkg_name,
                        "version": pkg_version,
                    },
                    timeout=120,
                )
            except httpx.TimeoutException:
                console.print("[red]Upload timed out.[/red]")
                raise SystemExit(1)

        if r.status_code == 201:
            console.print(f"  [green]✓ {file.name} uploaded successfully.[/green]")
        elif r.status_code == 401:
            console.print(
                "[red]Invalid API key.[/red] Run [bold]hivemind reg login[/bold] again."
            )
            raise SystemExit(1)
        elif r.status_code == 404:
            console.print(
                f"[red]Package '{pkg_name}' not found on registry.[/red]\n"
                f"This is unexpected — the package should have been created.\n"
                f"Try creating it manually at {REGISTRY_URL}"
            )
            raise SystemExit(1)
        elif r.status_code == 409:
            console.print(
                f"[yellow]Version {pkg_version} already exists.[/yellow] "
                "Bump version in pyproject.toml."
            )
            raise SystemExit(1)
        else:
            console.print(f"[red]Upload failed ({r.status_code}):[/red] {r.text}")
            raise SystemExit(1)

    # Check verification status for the version
    console.print(f"\n[dim]Checking verification status...[/dim]")
    poll_deadline = time.time() + 120
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Verifying...", total=None)
        while time.time() < poll_deadline:
            time.sleep(3)
            try:
                sr = client.get(
                    f"/api/v1/packages/{pkg_name}/versions/{pkg_version}/status"
                )
            except Exception:
                continue
            if sr.status_code != 200:
                # Status endpoint may not exist yet; check the version directly
                try:
                    vr = client.get(f"/api/v1/packages/{pkg_name}/{pkg_version}")
                    if vr.status_code == 200:
                        vdata = vr.json()
                        vstatus = vdata.get("verification_status", "")
                        if vstatus == "passed" or vdata.get("published"):
                            progress.stop()
                            console.print(
                                f"\n[green]✓ {pkg_name}@{pkg_version} published![/green]\n"
                                f"  Install: [bold]pip install "
                                f"--index-url {REGISTRY_URL}/simple/ {pkg_name}[/bold]"
                            )
                            return 0
                except Exception:
                    pass
                continue

            status_data = sr.json()
            status = status_data.get("verification_status")

            if status == "passed":
                progress.stop()
                tool_count = status_data.get("tool_count", 0)
                console.print(
                    f"\n[green]✓ {pkg_name}@{pkg_version} published![/green] "
                    f"({tool_count} tool(s) registered)\n"
                    f"  Install: [bold]pip install "
                    f"--index-url {REGISTRY_URL}/simple/ {pkg_name}[/bold]"
                )
                return 0
            elif status == "failed":
                progress.stop()
                report = status_data.get("verification_report", {})
                console.print(
                    f"\n[red]✗ Verification failed:[/red]\n"
                    f"{json.dumps(report, indent=2)}"
                )
                raise SystemExit(1)
            else:
                progress.update(
                    task,
                    description=f"Verifying... ({status or 'pending'})",
                )
        else:
            progress.stop()
            console.print(
                "[yellow]Verification timed out.[/yellow] "
                "The upload succeeded but verification is still running.\n"
                "Check status: "
                f"[bold]hivemind reg versions {pkg_name}[/bold]"
            )

    return 0


# ── search ─────────────────────────────────────────────────────────────────


def cmd_search(args):
    query = args.query
    verified_only = getattr(args, "verified", False)
    limit = getattr(args, "limit", 10)

    client = RegistryClient()
    params: dict = {"q": query, "limit": limit}
    if verified_only:
        params["verified"] = "true"

    try:
        r = client.get("/api/v1/search", params=params)
        r.raise_for_status()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    data = r.json()
    packages = data.get("packages") or data.get("results") or []
    if not packages:
        console.print("[dim]No results.[/dim]")
        return 0

    table = Table(show_header=True, header_style="bold")
    table.add_column("Package")
    table.add_column("Version")
    table.add_column("Downloads", justify="right")
    table.add_column("", justify="center")  # verified badge
    for p in packages:
        badge = "[green]✓[/green]" if p.get("verified") else ""
        table.add_row(
            p["name"],
            p.get("latest_version") or "—",
            str(p.get("total_downloads") or 0),
            badge,
        )
    console.print(table)
    return 0


# ── info ───────────────────────────────────────────────────────────────────


def cmd_info(args):
    name = args.package
    client = RegistryClient()
    try:
        r = client.get(f"/api/v1/packages/{name}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    if r.status_code == 404:
        console.print(f"[red]Package '{name}' not found.[/red]")
        raise SystemExit(1)
    r.raise_for_status()

    d = r.json()
    console.print(f"[bold]Name:[/bold]         {d['name']}")
    console.print(f"[bold]Description:[/bold]  {d.get('description') or '—'}")
    console.print(f"[bold]Latest:[/bold]       {d.get('latest_version') or '—'}")
    console.print(f"[bold]Downloads:[/bold]    {d.get('total_downloads') or 0}")
    console.print(f"[bold]Verified:[/bold]     {'Yes' if d.get('verified') else 'No'}")
    console.print(
        f"[bold]Install:[/bold]      pip install "
        f"--index-url {REGISTRY_URL}/simple/ {name}"
    )
    return 0


# ── versions ───────────────────────────────────────────────────────────────


def cmd_versions(args):
    name = args.package
    client = RegistryClient()
    try:
        r = client.get(f"/api/v1/packages/{name}/versions")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    if r.status_code == 404:
        console.print(f"[red]Package '{name}' not found.[/red]")
        raise SystemExit(1)
    r.raise_for_status()

    versions = r.json().get("versions", [])
    table = Table(show_header=True, header_style="bold")
    table.add_column("Version")
    table.add_column("Published")
    table.add_column("Downloads", justify="right")
    table.add_column("Status")
    table.add_column("Yanked", justify="center")
    for v in versions:
        yanked = "[red]yanked[/red]" if v.get("yanked") else ""
        uploaded = v.get("uploaded_at") or "—"
        if uploaded != "—":
            uploaded = uploaded[:10]
        table.add_row(
            v["version"],
            uploaded,
            str(v.get("download_count") or 0),
            v.get("verification_status") or "—",
            yanked,
        )
    console.print(table)
    return 0


# ── yank ───────────────────────────────────────────────────────────────────


def cmd_yank(args):
    name = args.package
    version = args.version
    reason = args.reason
    token = require_token()
    client = RegistryClient(token)

    try:
        r = client.post(
            f"/api/v1/packages/{name}/{version}/yank",
            json={"reason": reason},
        )
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    if r.status_code == 401:
        console.print("[red]Not authorized.[/red]")
        raise SystemExit(1)
    r.raise_for_status()
    console.print(f"[green]✓ Yanked {name}@{version}.[/green]")
    return 0
