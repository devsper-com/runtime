"""Devsper CLI — self-evolving AI workflow engine."""
from __future__ import annotations

import getpass
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

import click

# ── Provider definitions (mirrors credentials.rs) ────────────────────────────

_SERVICE = "devsper"

_PROVIDERS: dict[str, list[dict]] = {
    "anthropic":     [{"name": "api_key",    "env": "ANTHROPIC_API_KEY",        "secret": True}],
    "openai":        [{"name": "api_key",    "env": "OPENAI_API_KEY",           "secret": True}],
    "github":        [{"name": "token",      "env": "GITHUB_TOKEN",             "secret": True}],
    "zai": [
        {"name": "api_key",  "env": "ZAI_API_KEY",  "secret": True},
        {"name": "base_url", "env": "ZAI_BASE_URL",  "secret": False, "optional": True, "default": "https://api.z.ai/v1"},
    ],
    "azure-openai": [
        {"name": "api_key",    "env": "AZURE_OPENAI_API_KEY",     "secret": True},
        {"name": "endpoint",   "env": "AZURE_OPENAI_ENDPOINT",    "secret": False},
        {"name": "deployment", "env": "AZURE_OPENAI_DEPLOYMENT",  "secret": False},
        {"name": "api_version","env": "AZURE_OPENAI_API_VERSION", "secret": False, "optional": True, "default": "2024-02-01"},
    ],
    "azure-foundry": [
        {"name": "api_key",    "env": "AZURE_FOUNDRY_API_KEY",    "secret": True},
        {"name": "endpoint",   "env": "AZURE_FOUNDRY_ENDPOINT",   "secret": False},
        {"name": "deployment", "env": "AZURE_FOUNDRY_DEPLOYMENT", "secret": False},
    ],
    "litellm": [
        {"name": "base_url", "env": "LITELLM_BASE_URL", "secret": False},
        {"name": "api_key",  "env": "LITELLM_API_KEY",  "secret": True, "optional": True, "default": ""},
    ],
    "ollama":   [{"name": "host",     "env": "OLLAMA_HOST",       "secret": False, "optional": True, "default": "http://localhost:11434"}],
    "lmstudio": [
        {"name": "base_url", "env": "LMSTUDIO_BASE_URL", "secret": False, "optional": True, "default": "http://localhost:1234"},
        {"name": "api_key",  "env": "LMSTUDIO_API_KEY",  "secret": True,  "optional": True, "default": ""},
    ],
}

# ── Keychain helpers ──────────────────────────────────────────────────────────

def _kget(provider: str, field: str) -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(_SERVICE, f"{provider}:{field}")
    except Exception:
        return None

def _kset(provider: str, field: str, value: str) -> None:
    try:
        import keyring
        keyring.set_password(_SERVICE, f"{provider}:{field}", value)
    except Exception as e:
        click.echo(f"Warning: keychain save failed for {provider}:{field}: {e}", err=True)

def _kdel(provider: str, field: str) -> bool:
    try:
        import keyring
        keyring.delete_password(_SERVICE, f"{provider}:{field}")
        return True
    except Exception:
        return False

# ── Root ─────────────────────────────────────────────────────────────────────

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"], "max_content_width": 100}

@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(package_name="devsper")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """AI swarm runtime built in Rust.

    \b
    Give it a task — it breaks it into a graph of steps, runs them in
    parallel across your LLM provider, and returns the result.

    \b
    Quick start:
      devsper swarm "write a blog post about Rust"
      devsper run workflow.devsper --input topic="climate change"

    \b
    Providers (set via env or keychain):
      ANTHROPIC_API_KEY   OPENAI_API_KEY      GITHUB_TOKEN
      LMSTUDIO_BASE_URL   OLLAMA_HOST         LITELLM_BASE_URL
      ZAI_API_KEY         AZURE_OPENAI_*      AZURE_FOUNDRY_*

    \b
    Shell completions:
      bash:  eval "$(_DEVSPER_COMPLETE=bash_source devsper)"
      zsh:   eval "$(_DEVSPER_COMPLETE=zsh_source devsper)"
      fish:  eval (env _DEVSPER_COMPLETE=fish_source devsper)
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

# ── run ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("task")
@click.option("-o", "--output", default=None, type=click.Path(),
              help="Output directory (default: temp dir).")
@click.option("--model", default=None, metavar="MODEL",
              help="LLM model (e.g. google/gemma-4-e4b, claude-sonnet-4-6).")
@click.option("--workers", default=4, show_default=True, type=int,
              help="Parallel worker count.")
@click.option("--no-plan", is_flag=True, default=False,
              help="Skip planning step, run as single task.")
def swarm(task: str, output: Optional[str], model: Optional[str], workers: int, no_plan: bool) -> None:
    """Run any task through the AI swarm.

    \b
    The swarm plans the task into parallel subtasks, executes them
    concurrently, and writes all results to an output directory.

    \b
    Examples:
      devsper swarm "write a research paper on quantum computing"
      devsper swarm "build a todo app with Redis" --model google/gemma-4-e4b
      devsper swarm "analyze this codebase" -o ./results --no-plan
    """
    import json as _json
    import os
    import re
    import tempfile

    from devsper._core import NodeSpec, run_specs

    click.echo(f"Task: {task}")

    if not no_plan:
        click.echo("Planning subtasks...")
        plan_prompt = (
            "Break this task into 3-5 independent subtasks for parallel AI execution.\n"
            f"Task: {task}\n\n"
            "Return ONLY a valid JSON array, no explanation:\n"
            '[{"id":"step1","name":"short name","prompt":"full prompt","depends_on":[]}]'
        )
        plan_spec = NodeSpec(plan_prompt, model=model)
        plan_result = run_specs([plan_spec])
        plan_text = next(iter(plan_result.values()), "")

        match = re.search(r"\[.*?\]", plan_text, re.DOTALL)
        steps: list[dict] = []
        if match:
            try:
                steps = _json.loads(match.group())
            except Exception:
                pass

        if steps:
            click.echo(f"Plan: {len(steps)} steps")
            id_to_spec: dict[str, NodeSpec] = {}
            for step in steps:
                deps = [id_to_spec[d] for d in step.get("depends_on", []) if d in id_to_spec]
                spec = NodeSpec(step["prompt"], model=model, depends_on=deps or None)
                id_to_spec[step["id"]] = spec
            specs = list(id_to_spec.values())
            names = [s.get("name", s["id"]) for s in steps]
        else:
            click.echo("Plan parse failed — running as single task.")
            specs = [NodeSpec(task, model=model)]
            names = ["result"]
    else:
        specs = [NodeSpec(task, model=model)]
        names = ["result"]

    click.echo(f"Executing {len(specs)} task(s) in parallel...")
    results = run_specs(specs)

    out_dir = output or tempfile.mkdtemp(prefix="devsper-swarm-")
    os.makedirs(out_dir, exist_ok=True)

    for (node_id, content), name in zip(results.items(), names):
        safe_name = re.sub(r"[^\w\-]", "_", name)
        with open(os.path.join(out_dir, f"{safe_name}.md"), "w") as f:
            f.write(f"# {name}\n\n{content}\n")

    combined = "\n\n---\n\n".join(
        f"# {n}\n\n{c}" for n, c in zip(names, results.values())
    )
    combined_path = os.path.join(out_dir, "combined.md")
    with open(combined_path, "w") as f:
        f.write(f"# {task}\n\n{combined}\n")

    click.echo(f"\nDone → {out_dir}/")
    click.echo(f"combined: {combined_path}")


@cli.command()
@click.argument("workflow", type=click.Path(exists=True, dir_okay=False))
@click.option("--input", "-i", "inputs", multiple=True, metavar="KEY=VALUE",
              help="Workflow input variable (repeatable).")
@click.option("--cluster", metavar="ADDR", help="Cluster address to submit the run to.")
@click.option("--inspect-socket", metavar="PATH", type=click.Path(),
              help="Unix socket path for TUI inspection.")
def run(workflow: str, inputs: tuple, cluster: Optional[str], inspect_socket: Optional[str]) -> None:
    """Run a .devsper workflow file.

    \b
    Examples:
      devsper run pipeline.devsper
      devsper run pipeline.devsper -i topic="climate change" -i depth=3
    """
    from devsper._core import run as _run

    parsed: dict[str, str] = {}
    for kv in inputs:
        if "=" not in kv:
            raise click.BadParameter(f"expected KEY=VALUE, got '{kv}'", param_hint="--input/-i")
        k, v = kv.split("=", 1)
        parsed[k] = v

    results = _run(workflow, parsed or None)
    click.echo(json.dumps(results, indent=2))

# ── compile ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("workflow", type=click.Path(exists=True, dir_okay=False))
@click.option("--embed", is_flag=True, help="Embed runtime into a standalone binary.")
@click.option("-o", "--output", metavar="FILE", type=click.Path(),
              help="Output file path.")
def compile(workflow: str, embed: bool, output: Optional[str]) -> None:
    """Compile a .devsper file to bytecode or standalone binary.

    \b
    Examples:
      devsper compile pipeline.devsper
      devsper compile pipeline.devsper -o pipeline.bin
      devsper compile pipeline.devsper --embed -o pipeline
    """
    from devsper._core import compile as _compile

    out_path = _compile(workflow, embed, output)
    click.echo(f"Compiled: {out_path}")

# ── peer ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--listen", default="0.0.0.0:7000", show_default=True,
              help="Address to listen on.")
@click.option("--join", metavar="ADDR", help="Address of an existing cluster node to join.")
def peer(listen: str, join: Optional[str]) -> None:
    """Start a peer cluster node.

    \b
    Examples:
      devsper peer                               # start as coordinator
      devsper peer --join 10.0.0.2:7000          # join an existing cluster
      devsper peer --listen 0.0.0.0:7001 --join 10.0.0.2:7000
    """
    from devsper._core import peer as _peer

    _peer(listen, join)

# ── inspect ──────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("run_id")
def inspect(run_id: str) -> None:
    """Inspect a running workflow via its Unix socket.

    RUN_ID is the run ID or socket path returned by devsper run.
    """
    from devsper._core import inspect as _inspect

    _inspect(run_id)

# ── credentials ──────────────────────────────────────────────────────────────

@cli.group(context_settings=CONTEXT_SETTINGS)
def credentials() -> None:
    """Manage provider credentials in the OS keychain."""

@credentials.command("set")
@click.argument("provider", type=click.Choice(sorted(_PROVIDERS), case_sensitive=False))
def credentials_set(provider: str) -> None:
    """Interactively set credentials for a provider.

    \b
    Supported providers:
      anthropic, openai, github, zai, azure-openai, azure-foundry,
      litellm, ollama, lmstudio

    \b
    Examples:
      devsper credentials set anthropic
      devsper credentials set azure-openai
    """
    fields = _PROVIDERS[provider]
    click.echo(f"Setting credentials for '{provider}':")
    for field in fields:
        default = field.get("default")
        optional = field.get("optional", False)
        if default is not None and default != "":
            prompt_text = f"  {field['name']} [default: {default}]: "
        elif optional:
            prompt_text = f"  {field['name']} (optional, Enter to skip): "
        else:
            prompt_text = f"  {field['name']}: "

        if field.get("secret"):
            value = getpass.getpass(prompt_text)
        else:
            value = input(prompt_text)

        value = value.strip()
        if not value:
            if default is not None:
                if default == "":
                    continue
                value = default
            else:
                click.echo(f"  Skipping empty required field '{field['name']}'.", err=True)
                continue

        _kset(provider, field["name"], value)
        click.echo(f"  Saved {field['name']}.")
    click.echo("Done.")

@credentials.command("list")
def credentials_list() -> None:
    """List all providers and their credential status."""
    col = [16, 12, 8, 26]
    sep = "+-" + "-+-".join("-" * w for w in col) + "-+"
    click.echo(sep)
    click.echo(f"| {'provider':<{col[0]}} | {'field':<{col[1]}} | {'status':<{col[2]}} | {'env_var':<{col[3]}} |")
    click.echo(sep)
    for provider, fields in _PROVIDERS.items():
        for field in fields:
            in_kc  = _kget(provider, field["name"]) is not None
            in_env = field["env"] in os.environ
            if in_kc:       status = "keychain"
            elif in_env:    status = "env"
            elif field.get("optional"): status = "default"
            else:           status = "unset"
            click.echo(f"| {provider:<{col[0]}} | {field['name']:<{col[1]}} | {status:<{col[2]}} | {field['env']:<{col[3]}} |")
    click.echo(sep)

@credentials.command("remove")
@click.argument("provider", type=click.Choice(sorted(_PROVIDERS), case_sensitive=False))
def credentials_remove(provider: str) -> None:
    """Remove all stored credentials for a provider from the keychain."""
    for field in _PROVIDERS[provider]:
        if _kdel(provider, field["name"]):
            click.echo(f"Removed {provider}:{field['name']}")
    click.echo(f"Credentials for '{provider}' removed.")

# ── auth ─────────────────────────────────────────────────────────────────────

@cli.group(context_settings=CONTEXT_SETTINGS)
def auth() -> None:
    """Authentication helpers."""

_GH_CLIENT_ID_DEFAULT = "Ov23li4your_client_id"
_GH_DEVICE_URL = "https://github.com/login/device/code"
_GH_TOKEN_URL  = "https://github.com/login/oauth/access_token"

@auth.command("github")
def auth_github() -> None:
    """Authenticate with GitHub via the device authorization flow.

    Opens a browser URL and waits for you to enter a short code,
    then stores the resulting token in the OS keychain.
    """
    client_id = os.environ.get("DEVSPER_GITHUB_CLIENT_ID", _GH_CLIENT_ID_DEFAULT)
    if client_id == _GH_CLIENT_ID_DEFAULT:
        click.echo(
            "Warning: using placeholder GitHub client_id. "
            "Set DEVSPER_GITHUB_CLIENT_ID with your OAuth App client_id.",
            err=True,
        )

    def _post(url: str, data: dict) -> dict:
        body = urllib.parse.urlencode(data).encode()
        req  = urllib.request.Request(url, data=body, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    step1      = _post(_GH_DEVICE_URL, {"client_id": client_id, "scope": "read:user"})
    user_code  = step1["user_code"]
    verify_uri = step1["verification_uri"]
    device_code = step1["device_code"]
    interval   = int(step1.get("interval", 5))
    expires_in = int(step1.get("expires_in", 900))

    click.echo(f"\n=== GitHub Login ===")
    click.echo(f"Open:  {verify_uri}")
    click.echo(f"Code:  {user_code}\n")
    click.echo("Waiting for authorization...")

    deadline = time.monotonic() + expires_in
    while True:
        if time.monotonic() >= deadline:
            raise click.ClickException("Timed out. Run the command again.")
        time.sleep(interval)
        data = _post(_GH_TOKEN_URL, {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        err = data.get("error")
        if err == "authorization_pending": continue
        elif err == "slow_down": interval += 5; continue
        elif err == "expired_token":  raise click.ClickException("Code expired. Run again.")
        elif err == "access_denied":  raise click.ClickException("Authorization denied.")
        elif err:                     raise click.ClickException(f"GitHub error: {err}")
        token = data.get("access_token")
        if token:
            _kset("github", "token", token)
            click.echo("GitHub authentication successful. Token stored in keychain.")
            return

@auth.command("status")
def auth_status() -> None:
    """Show authentication and configuration status for all providers."""
    col = [16, 32, 12]
    sep = "+-" + "-+-".join("-" * w for w in col) + "-+"
    click.echo(sep)
    click.echo(f"| {'provider':<{col[0]}} | {'configured fields':<{col[1]}} | {'source':<{col[2]}} |")
    click.echo(sep)
    for provider, fields in _PROVIDERS.items():
        set_fields: list[str] = []
        source = "unset"
        for field in fields:
            in_kc  = _kget(provider, field["name"]) is not None
            in_env = field["env"] in os.environ
            if in_kc:
                set_fields.append(field["name"]); source = "keychain"
            elif in_env:
                set_fields.append(field["name"])
                if source == "unset": source = "env"
        fields_str = ", ".join(set_fields) if set_fields else "-"
        if len(fields_str) > col[1]: fields_str = fields_str[:col[1]-3] + "..."
        click.echo(f"| {provider:<{col[0]}} | {fields_str:<{col[1]}} | {source:<{col[2]}} |")
    click.echo(sep)

# ── eval ─────────────────────────────────────────────────────────────────────

@cli.group(context_settings=CONTEXT_SETTINGS)
def eval() -> None:
    """Evaluate a workflow against a JSONL dataset."""

@eval.command("run")
@click.option("--workflow", required=True, metavar="FILE",
              type=click.Path(exists=True, dir_okay=False), help="Workflow file.")
@click.option("--dataset",  required=True, metavar="FILE",
              type=click.Path(exists=True, dir_okay=False), help="JSONL dataset file.")
@click.option("--output", default="eval_results.jsonl", show_default=True,
              metavar="FILE", help="Output JSONL results file.")
def eval_run(workflow: str, dataset: str, output: str) -> None:
    """Run a workflow against every case in a JSONL dataset.

    Each line of the dataset should be a JSON object. Inputs are taken from:
      {"inputs": {"key": "val"}}   — explicit inputs map
      {"input": "text"}            — shorthand, becomes {"query": "text"}
      {"key": "val", ...}          — whole object used as inputs

    \b
    Examples:
      devsper eval run --workflow pipeline.devsper --dataset cases.jsonl
      devsper eval run --workflow pipeline.devsper --dataset cases.jsonl --output results.jsonl
    """
    from devsper._core import run as _run

    total = succeeded = 0
    with open(dataset) as df, open(output, "a") as rf:
        for i, line in enumerate(df):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            inputs = _normalize_inputs(raw)
            click.echo(f"  Case {i + 1}: ", nl=False)
            t0 = time.monotonic()
            try:
                results  = _run(workflow, inputs or None)
                latency  = int((time.monotonic() - t0) * 1000)
                out_str  = json.dumps(results)
                success  = True; stderr_str = ""; exit_code = 0
                click.echo(f"ok ({latency}ms)")
            except Exception as exc:
                latency  = int((time.monotonic() - t0) * 1000)
                out_str  = ""; success = False; stderr_str = str(exc); exit_code = 1
                click.echo(f"FAIL ({latency}ms)")
                preview = str(exc)[:80]
                click.echo(f"    error: {preview}")
            rf.write(json.dumps({
                "inputs": inputs, "output": out_str,
                "exit_code": exit_code, "latency_ms": latency,
                "success": success, "stderr": stderr_str,
            }) + "\n")
            rf.flush()
            total += 1
            if success:
                succeeded += 1

    click.echo(f"\nEval complete: {succeeded}/{total} passed")
    click.echo(f"Results written to: {output}")

@eval.command("report")
@click.option("--input", "input_file", default="eval_results.jsonl", show_default=True,
              metavar="FILE", help="Input JSONL results file.")
@click.option("--last", default=0, type=int, show_default=True,
              help="Show only the last N results (0 = all).")
def eval_report(input_file: str, last: int) -> None:
    """Print a summary report from eval results.

    \b
    Examples:
      devsper eval report
      devsper eval report --input results.jsonl --last 20
    """
    entries: list[dict] = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try: entries.append(json.loads(line))
                except json.JSONDecodeError: pass

    if last > 0:
        entries = entries[-last:]
    if not entries:
        click.echo(f"No eval results found in '{input_file}'")
        return

    total     = len(entries)
    succeeded = sum(1 for e in entries if e.get("success"))
    rate      = succeeded / total * 100
    avg_ms    = sum(e.get("latency_ms", 0) for e in entries) // total

    click.echo("=== Eval Report ===")
    click.echo(f"  Total cases:  {total}")
    click.echo(f"  Success rate: {succeeded}/{total} ({rate:.1f}%)")
    click.echo(f"  Avg latency:  {avg_ms}ms\n")

    col = [30, 8, 12, 80]
    sep = "+-" + "-+-".join("-" * w for w in col) + "-+"
    click.echo(sep)
    click.echo(f"| {'inputs':<{col[0]}} | {'success':<{col[1]}} | {'latency_ms':<{col[2]}} | {'output preview':<{col[3]}} |")
    click.echo(sep)
    for e in entries:
        inp = e.get("inputs", {})
        inp_str = ", ".join(f"{k}={v}" for k, v in inp.items()) if isinstance(inp, dict) else str(inp)
        click.echo(
            f"| {_trunc(inp_str, col[0]):<{col[0]}} "
            f"| {'yes' if e.get('success') else 'no':<{col[1]}} "
            f"| {str(e.get('latency_ms', 0)):<{col[2]}} "
            f"| {_trunc(str(e.get('output', '')).replace(chr(10), ' '), col[3]):<{col[3]}} |"
        )
    click.echo(sep)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_inputs(raw: dict) -> dict[str, str]:
    if isinstance(raw.get("inputs"), dict):
        return {k: str(v) for k, v in raw["inputs"].items()}
    if isinstance(raw.get("input"), str):
        return {"query": raw["input"]}
    return {k: str(v) for k, v in raw.items() if isinstance(v, (str, int, float))}

def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    cli()

if __name__ == "__main__":
    main()
