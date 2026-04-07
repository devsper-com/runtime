"""Developer onboarding: devsper init and devsper doctor."""

import os
import sys
from pathlib import Path

# Provider choices for interactive init: (id, display_name, env_var, planner_models, worker_models)
PROVIDER_REGISTRY: list[tuple[str, str, str | None, list[str], list[str]]] = [
    (
        "auto",
        "Auto (detect from environment)",
        None,
        ["auto"],
        ["auto"],
    ),
    (
        "openai",
        "OpenAI (GPT-4o, GPT-4o-mini, etc.)",
        "OPENAI_API_KEY",
        ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o3-mini"],
        ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview", "o3-mini"],
    ),
    (
        "anthropic",
        "Anthropic (Claude)",
        "ANTHROPIC_API_KEY",
        [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
    ),
    (
        "gemini",
        "Google (Gemini)",
        "GOOGLE_API_KEY",
        ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"],
        ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-exp"],
    ),
    (
        "github",
        "GitHub (Copilot Models)",
        "GITHUB_TOKEN",
        ["github:copilot"],
        ["github:copilot"],
    ),
    (
        "azure_openai",
        "Azure OpenAI",
        "AZURE_OPENAI_ENDPOINT",
        ["gpt-4o", "gpt-4o-mini"],
        ["gpt-4o", "gpt-4o-mini"],
    ),
    (
        "ollama",
        "Ollama (local)",
        "OLLAMA_HOST",
        ["llama3"],
        ["llama3"],
    ),
    (
        "mock",
        "Mock (no API, for testing)",
        None,
        ["mock"],
        ["mock"],
    ),
]


def _provider_choices_for_display() -> list[tuple[str, str]]:
    """Return [(id, display_line), ...] for menu."""
    return [(pid, display) for pid, display, _env, _pl, _wk in PROVIDER_REGISTRY]


def _select_option(prompt: str, choices: list[tuple[str, str]], default_index: int = 0) -> str:
    """Show numbered choices and return selected id. Uses 1-based input."""
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    for i, (_id, label) in enumerate(choices, start=1):
        console.print(f"  [cyan]{i}[/]. {label}")
    default = default_index + 1
    raw = Prompt.ask(prompt, default=str(default))
    try:
        idx = int(raw)
        if 1 <= idx <= len(choices):
            return choices[idx - 1][0]
    except ValueError:
        pass
    return choices[default_index][0]


def _select_model(prompt: str, model_ids: list[str], default_index: int = 0) -> str:
    """Show numbered model list and return selected model id."""
    from rich.console import Console
    from rich.prompt import Prompt

    console = Console()
    for i, mid in enumerate(model_ids, start=1):
        console.print(f"  [cyan]{i}[/]. {mid}")
    default = default_index + 1
    raw = Prompt.ask(prompt, default=str(default))
    try:
        idx = int(raw)
        if 1 <= idx <= len(model_ids):
            return model_ids[idx - 1]
    except ValueError:
        pass
    return model_ids[default_index]


def _build_init_toml(
    *,
    workers: int = 4,
    planner: str = "auto",
    worker: str = "auto",
    memory_enabled: bool = True,
    tools_top_k: int = 12,
    speculative_execution: bool = False,
    cache_enabled: bool = False,
    adaptive_planning: bool = False,
    adaptive_execution: bool = False,
    max_iterations: int = 10,
    providers_toml: str = "",
) -> str:
    """Build [swarm] [models] [memory] [tools] TOML snippet."""
    base = f"""[swarm]
workers = {workers}
speculative_execution = {str(speculative_execution).lower()}
cache_enabled = {str(cache_enabled).lower()}
adaptive_planning = {str(adaptive_planning).lower()}
adaptive_execution = {str(adaptive_execution).lower()}
max_iterations = {max_iterations}

[models]
planner = "{planner}"
worker = "{worker}"

[memory]
enabled = {str(memory_enabled).lower()}

[tools]
top_k = {tools_top_k}
"""
    if providers_toml and not providers_toml.endswith("\n"):
        providers_toml += "\n"
    return base + ("\n" if providers_toml and not base.endswith("\n") else "") + providers_toml


def _run_init_interactive(cwd: Path) -> tuple[str, dict[str, str]]:
    """
    CLI interactive flow: provider → GitHub device login or continue → planner/worker → options.
    Returns (toml_content, api_keys to write to .env).
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, IntPrompt, Prompt

    console = Console()
    api_keys: dict[str, str] = {}

    console.print()
    console.print(
        Panel(
            "[bold]devsper project setup[/]\n\nWe'll create [cyan]devsper.toml[/].",
            title="Welcome",
            border_style="green",
        )
    )
    console.print()

    choices = _provider_choices_for_display()
    provider_id = _select_option("Select model provider", choices, default_index=0)
    console.print(f"  [dim]Using provider: {provider_id}[/]\n")

    providers_toml = ""
    if provider_id == "ollama":
        default_ollama_host = os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
        ollama_host = Prompt.ask("OLLAMA_HOST (Ollama base URL)", default=default_ollama_host)
        if str(ollama_host).strip():
            providers_toml = f"""
[providers]
[providers.ollama]
enabled = true
base_url = "{str(ollama_host).strip()}"
"""
            api_keys["OLLAMA_HOST"] = str(ollama_host).strip()

    # GitHub: device flow (show code, open browser, poll) if no token and client_id set
    if provider_id == "github" and not os.environ.get("GITHUB_TOKEN"):
        try:
            from devsper.cli.github_oauth import (
                GITHUB_DEVICE_CLIENT_ID,
                GitHubDeviceFlowError,
                run_device_flow_cli,
            )
            if GITHUB_DEVICE_CLIENT_ID:
                token = run_device_flow_cli(client_id=GITHUB_DEVICE_CLIENT_ID, open_browser=True)
                api_keys["GITHUB_TOKEN"] = token
                os.environ["GITHUB_TOKEN"] = token
                console.print("[green]✔[/] GitHub login successful.")
            else:
                console.print("[yellow]Paste a GitHub token (e.g. from https://github.com/settings/tokens)[/]")
                from rich.prompt import Prompt
                raw = Prompt.ask("GITHUB_TOKEN", password=True, default="")
                if raw.strip():
                    api_keys["GITHUB_TOKEN"] = raw.strip()
                    os.environ["GITHUB_TOKEN"] = raw.strip()
        except GitHubDeviceFlowError as e:
            console.print(f"[red]GitHub login failed: {e}[/]")
            from rich.prompt import Prompt
            raw = Prompt.ask("Paste GITHUB_TOKEN (or leave blank)", password=True, default="")
            if raw.strip():
                api_keys["GITHUB_TOKEN"] = raw.strip()
                os.environ["GITHUB_TOKEN"] = raw.strip()

    planner_model = "auto"
    worker_model = "auto"
    for pid, _display, _env, planner_models, worker_models in PROVIDER_REGISTRY:
        if pid != provider_id:
            continue
        if len(planner_models) > 1:
            planner_model = _select_model(
                "Planner model (for task decomposition)",
                planner_models,
                default_index=min(1, len(planner_models) - 1),
            )
        else:
            planner_model = planner_models[0]
        if len(worker_models) > 1:
            worker_model = _select_model(
                "Worker model (for executing subtasks)",
                worker_models,
                default_index=min(1, len(worker_models) - 1),
            )
        else:
            worker_model = worker_models[0]
        break

    workers = 4
    if Confirm.ask("Set number of workers?", default=True):
        workers = IntPrompt.ask("Workers", default=4)
        workers = max(1, min(32, workers))

    memory_enabled = Confirm.ask("Enable memory (store results for context)?", default=True)
    tools_top_k = 12
    if Confirm.ask("Limit tools per task (top_k)?", default=True):
        tools_top_k = IntPrompt.ask("top_k (0 = no limit)", default=12)
        tools_top_k = max(0, min(50, tools_top_k))

    speculative = Confirm.ask("Enable speculative execution?", default=False)
    cache = Confirm.ask("Enable task cache?", default=False)
    adaptive_planning = Confirm.ask("Enable adaptive planning?", default=False)
    adaptive_execution = Confirm.ask("Enable adaptive execution?", default=False)

    toml_content = _build_init_toml(
        workers=workers,
        planner=planner_model,
        worker=worker_model,
        memory_enabled=memory_enabled,
        tools_top_k=tools_top_k,
        speculative_execution=speculative,
        cache_enabled=cache,
        adaptive_planning=adaptive_planning,
        adaptive_execution=adaptive_execution,
        providers_toml=providers_toml,
    )

    return toml_content, api_keys


def run_init(interactive: bool = True) -> int:
    """
    Set up a new project: create devsper.toml only (no dataset, no example workflow).
    When interactive=True, CLI prompts for provider, models, workers, and options.
    GitHub: device login (code + open browser) when no GITHUB_TOKEN.
    """
    cwd = Path.cwd()
    errors: list[str] = []

    created_toml = False
    toml_path = cwd / "devsper.toml"
    api_keys: dict[str, str] = {}

    if toml_path.exists():
        errors.append("devsper.toml already exists")
    else:
        if interactive:
            try:
                toml_content, api_keys = _run_init_interactive(cwd)
                try:
                    toml_path.write_text(toml_content, encoding="utf-8")
                    created_toml = True
                except Exception as e:
                    errors.append(f"Failed to create devsper.toml: {e}")
                if api_keys:
                    _write_env_file(cwd, api_keys)
            except (KeyboardInterrupt, EOFError):
                print("\nInit cancelled.", file=sys.stderr)
                return 130
        else:
            providers_toml = ""
            planner_choice = "auto"
            worker_choice = "auto"
            ollama_host = os.environ.get("OLLAMA_HOST")
            if ollama_host and str(ollama_host).strip():
                providers_toml = f"""
[providers]
[providers.ollama]
enabled = true
base_url = "{str(ollama_host).strip()}"
"""
                # Avoid "auto" routing (which picks OpenAI/Claude model ids) when using a local Ollama server.
                planner_choice = "llama3"
                worker_choice = "llama3"
            toml_content = _build_init_toml(
                workers=4,
                planner=planner_choice,
                worker=worker_choice,
                memory_enabled=True,
                tools_top_k=12,
                providers_toml=providers_toml,
            )
            try:
                toml_path.write_text(toml_content, encoding="utf-8")
                created_toml = True
            except Exception as e:
                errors.append(f"Failed to create devsper.toml: {e}")

    env_ok = _check_env_quiet()

    from rich.console import Console

    console = Console()
    if created_toml:
        console.print("[green]✔[/] devsper.toml created")
    if env_ok:
        console.print("[green]✔[/] environment check passed")
    elif not errors and created_toml:
        console.print(
            "[yellow]⚠[/] No API keys detected. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GOOGLE_API_KEY, or GITHUB_TOKEN (see devsper doctor)."
        )

    if errors:
        for e in errors:
            console.print(f"[red]✗[/] {e}", style="red")
        return 1

    # Offer to store API keys in credential store after setup
    env_to_cred = {
        "GITHUB_TOKEN": ("github", "token"),
        "OPENAI_API_KEY": ("openai", "api_key"),
        "ANTHROPIC_API_KEY": ("anthropic", "api_key"),
        "GOOGLE_API_KEY": ("gemini", "api_key"),
        "GEMINI_API_KEY": ("gemini", "api_key"),
        "AZURE_OPENAI_API_KEY": ("azure", "api_key"),
        "AZURE_OPENAI_ENDPOINT": ("azure", "endpoint"),
    }
    has_any_key = any(
        (api_keys.get(env_var) or os.environ.get(env_var))
        for env_var in env_to_cred
    )
    if interactive and created_toml and has_any_key:
        try:
            from rich.prompt import Confirm

            if Confirm.ask("\nWould you like to store your API keys securely now?", default=True):
                from devsper.credentials import set_credential

                stored = 0
                for env_var, (provider, key) in env_to_cred.items():
                    val = api_keys.get(env_var) or os.environ.get(env_var)
                    if val and str(val).strip():
                        set_credential(provider, key, str(val).strip())
                        stored += 1
                if stored:
                    console.print(f"[green]✔[/] Stored {stored} credential(s) securely")
        except (KeyboardInterrupt, EOFError):
            pass
        except Exception:
            pass

    console.print()
    console.print("Next steps:")
    console.print("  1) Set API keys if not already set (or use GitHub device login when choosing GitHub)")
    console.print("  2) Edit devsper.toml if needed")
    console.print('  3) Run: [cyan]devsper run "your task"[/]')
    return 0


def _write_env_file(cwd: Path, api_keys: dict[str, str]) -> None:
    """Append new API keys to .env in cwd (skip keys already present)."""
    if not api_keys:
        return
    env_path = cwd / ".env"
    lines: list[str] = []
    existing_keys: set[str] = set()
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").rstrip().splitlines()
        existing_keys = {ln.split("=", 1)[0].strip() for ln in lines if "=" in ln}
    for k, v in api_keys.items():
        if k not in existing_keys:
            lines.append(f'{k}="{v}"')
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _check_env_quiet() -> bool:
    """Return True if at least one provider env is set."""
    return bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("OLLAMA_HOST")
        or (os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"))
    )


def _check_plaintext_keys_in_toml(warnings: list[str]) -> None:
    """Warn (yellow) if API keys appear as plaintext in devsper.toml."""
    from devsper.config.config_loader import project_config_paths

    for p in project_config_paths():
        if not p.is_file():
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Grep-style: look for credential-like values (sk-, ghp_, https://)
        if '= "sk-' in raw or '="sk-' in raw:
            warnings.append(
                f"Possible API key (sk-...) found as plaintext in {p}; use 'devsper credentials set' and remove from TOML"
            )
        elif '= "ghp_' in raw or '="ghp_' in raw:
            warnings.append(
                f"Possible GitHub token found as plaintext in {p}; use 'devsper credentials set' and remove from TOML"
            )
        elif ('endpoint' in raw or 'api_key' in raw) and ('= "https://' in raw or '="https://' in raw):
            warnings.append(
                f"Possible endpoint/secret found as plaintext in {p}; use 'devsper credentials set' and remove from TOML"
            )
        break


def run_doctor() -> int:
    """
    Verify environment: GITHUB_TOKEN, OpenAI keys, config file, tool registry.
    Warn if plaintext keys found in TOML.
    """
    issues: list[str] = []
    ok: list[str] = []
    warnings: list[str] = []
    mcp_ok: list[str] = []
    mcp_warnings: list[str] = []

    if os.environ.get("GITHUB_TOKEN"):
        ok.append("GITHUB_TOKEN is set")
    else:
        issues.append("GITHUB_TOKEN not set (optional, for GitHub Models)")

    if os.environ.get("OPENAI_API_KEY"):
        ok.append("OPENAI_API_KEY is set")
    else:
        issues.append("OPENAI_API_KEY not set (optional)")

    if os.environ.get("OLLAMA_HOST"):
        ok.append("OLLAMA_HOST is set")

    from devsper.config.config_loader import project_config_paths

    found = False
    for p in project_config_paths():
        if p.is_file():
            ok.append(f"Config file found: {p}")
            found = True
            break
    if not found:
        issues.append("No project config (devsper.toml or workflow.devsper.toml) in cwd or parent")

    try:
        from devsper.tools.registry import list_tools

        tools = list_tools()
        ok.append(f"Tool registry: {len(tools)} tools loaded")
    except Exception as e:
        issues.append(f"Tool registry: {e}")

    try:
        from devsper.tools.scoring import get_default_score_store

        store = get_default_score_store()
        n_records = store.result_count()
        n_tools = store.tool_count()
        ok.append(f"Tool scoring database: {n_records} records, {n_tools} tools tracked")
        if n_tools > 0:
            scores = store.get_all_scores()
            with_10_plus = [s for s in scores if s.total_calls >= 10]
            poor = [s for s in with_10_plus if s.composite_score < 0.40]
            if with_10_plus and len(poor) / len(with_10_plus) > 0.20:
                warnings.append(
                    f"Over 20% of tools (10+ calls) are in poor state ({len(poor)}/{len(with_10_plus)}). Consider reviewing with 'devsper tools --poor'."
                )
            dead = [s for s in with_10_plus if s.success_rate == 0.0]
            for s in dead:
                warnings.append(
                    f"Tool '{s.tool_name}' has 0% success with {s.total_calls} calls. Consider: devsper tools reset {s.tool_name}"
                )
    except Exception:
        pass

    try:
        from devsper.memory.memory_store import get_default_store
        store = get_default_store()
        all_records = store.list_memory(limit=10000, include_archived=True)
        active = [r for r in all_records if not getattr(r, "archived", False)]
        archived_count = len(all_records) - len(active)
        ok.append(f"Memory: {len(active)} active, {archived_count} archived records")
        if len(active) > 1000:
            warnings.append(
                "Memory store has > 1000 non-archived records. Consider running 'devsper memory consolidate'."
            )
    except Exception as e:
        warnings.append(f"Memory store: {e}")

    # Memory provider health check
    try:
        import asyncio
        from devsper.memory.providers.factory import get_memory_provider
        provider = get_memory_provider()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    healthy = pool.submit(asyncio.run, provider.health()).result()
            else:
                healthy = loop.run_until_complete(provider.health())
        except Exception:
            healthy = False
        if healthy:
            ok.append(f"Memory provider: {provider.name} — healthy")
        else:
            warnings.append(
                f"Memory provider: {provider.name} — health check failed. "
                "Check credentials and connectivity."
            )
    except Exception as e:
        warnings.append(f"Memory provider health check failed: {e}")

    try:
        from devsper.knowledge.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph(store=get_default_store())
        kg.load()
        g = kg.graph
        n_nodes = g.number_of_nodes()
        n_edges = g.number_of_edges()
        try:
            from devsper.config import get_config
            base = get_config().data_dir
        except Exception:
            base = os.environ.get("DEVSPER_DATA_DIR", ".devsper")
        path = os.path.join(base, "knowledge_graph.json")
        last_updated = "unknown"
        if os.path.isfile(path):
            from datetime import datetime, timezone
            mtime = os.path.getmtime(path)
            last_updated = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        ok.append(f"Knowledge graph: {n_nodes} nodes, {n_edges} edges, last updated {last_updated}")
    except Exception as e:
        warnings.append(f"Knowledge graph: {e}")

    # v1.10.5: MCP and A2A
    try:
        from devsper.config import get_config
        cfg = get_config()
        mcp_servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
        for s in mcp_servers:
            sname = getattr(s, "name", "?")
            try:
                from devsper.tools.mcp import discover_mcp_tools
                adapters = discover_mcp_tools(s)
                mcp_ok.append(f"  {sname}: {len(adapters)} tools")
            except Exception as e:
                mcp_warnings.append(f"  {sname}: {e}")
        if not mcp_servers:
            mcp_ok.append("  (none configured — add [[mcp.servers]] to devsper.toml)")
        a2a_agents = getattr(getattr(cfg, "a2a", None), "agents", None) or []
        for a in a2a_agents:
            aname = getattr(a, "name", "?")
            url = getattr(a, "url", "")
            if not url:
                continue
            try:
                from devsper.agents.a2a.client import A2AClient
                import asyncio
                client = A2AClient()
                card = asyncio.run(client.get_agent_card(url))
                ok.append(f"A2A agent '{aname or card.name}': {len(card.skills)} skills")
            except Exception as e:
                warnings.append(f"A2A agent '{aname}': {e}")
    except Exception:
        pass

    try:
        from devsper.config import get_config
        cfg = get_config()
        nodes_mode = getattr(getattr(cfg, "nodes", None), "mode", "single")
        if nodes_mode == "distributed":
            try:
                import redis
                r = redis.from_url(getattr(getattr(cfg, "bus", None), "redis_url", "redis://localhost:6379"))
                r.ping()
                ok.append("Redis reachable (distributed mode)")
            except ImportError:
                issues.append("Distributed mode requires: pip install devsper[distributed]")
            except Exception as e:
                issues.append(f"Redis not reachable: {e}")
            try:
                import fastapi
                import uvicorn
                ok.append("fastapi + uvicorn installed (RPC)")
            except ImportError:
                warnings.append("RPC endpoints need: pip install devsper[distributed]")
            if not getattr(getattr(cfg, "nodes", None), "rpc_token", None):
                warnings.append("nodes.rpc_token not set — RPC endpoints are unauthenticated")
        else:
            ok.append("Running in single-node mode — no cluster checks needed")
    except Exception:
        pass

    _check_plaintext_keys_in_toml(warnings)

    try:
        from devsper.runtime.run_history import RunHistory, HISTORY_DB
        history = RunHistory()
        stats = history.get_stats()
        n = stats.get("total_runs", 0)
        total_cost = stats.get("total_estimated_cost_usd", 0.0)
        if HISTORY_DB.exists():
            ok.append(f"Run history: {n} runs recorded, ${total_cost:.4f} total estimated spend")
        else:
            ok.append("Run history: DB not yet created (will be created on first run)")
        if n > 0:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            rows = history.list_runs(limit=50)
            for r in rows:
                started = getattr(r, "started_at", "") or ""
                if started < cutoff:
                    continue
                total = getattr(r, "total_tasks", 0) or 0
                failed = getattr(r, "failed_tasks", 0) or 0
                if total > 0 and (failed / total) > 0.50:
                    warnings.append(
                        f"Run {getattr(r, 'run_id', '?')[:24]}... had >50% task failure ({failed}/{total}) in last 7 days"
                    )
    except Exception as e:
        warnings.append(f"Run history: {e}")

    try:
        from devsper.cli.ui import console, devsperHeader, SectionHeader
        import devsper
        ver = getattr(devsper, "__version__", "?")
        console.print(devsperHeader(version=ver))
        console.print(SectionHeader("Health check"))
        for s in ok:
            console.print(f"  [hive.success]✓[/]  {s}")
        for s in issues:
            console.print(f"  [hive.error]✗[/]  {s}")
        for s in warnings:
            console.print(f"  [hive.warning]⚠[/]  {s}")
        console.print(SectionHeader("MCP Servers"))
        for s in mcp_ok:
            console.print(f"  [hive.success]✓[/]  {s}")
        for s in mcp_warnings:
            console.print(f"  [hive.warning]⚠[/]  {s}")
        if warnings or issues:
            console.print()
            console.print(f"  [hive.muted]{len(warnings)} warnings  ·  {len(issues)} errors[/]")
    except ImportError:
        from rich.console import Console
        c = Console()
        for s in ok:
            c.print(f"[green]✔[/] {s}")
        for s in issues:
            c.print(f"[red]✗[/] {s}", style="red")
        for s in warnings:
            c.print(f"[yellow]⚠[/] {s}", style="yellow")
        c.print("\nMCP Servers:")
        for s in mcp_ok:
            c.print(f"  [green]✔[/] {s}")
        for s in mcp_warnings:
            c.print(f"  [yellow]⚠[/] {s}", style="yellow")
    return 0 if not issues else 1
