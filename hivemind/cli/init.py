"""Developer onboarding: hivemind init and hivemind doctor."""

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
        "mock",
        "Mock (no API, for testing)",
        None,
        ["mock"],
        ["mock"],
    ),
]


def _provider_choices_for_display() -> list[tuple[str, str]]:
    """Return [(id, display_line), ...] for menu."""
    out: list[tuple[str, str]] = []
    for pid, display, env_var, _pl, _wk in PROVIDER_REGISTRY:
        env_note = f" (set {env_var})" if env_var else ""
        out.append((pid, f"{display}{env_note}"))
    return out


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
) -> str:
    """Build [swarm] [models] [memory] [tools] TOML snippet."""
    return f"""[swarm]
workers = {workers}

[models]
planner = "{planner}"
worker = "{worker}"

[memory]
enabled = {str(memory_enabled).lower()}

[tools]
top_k = {tools_top_k}
"""


EXAMPLE_WORKFLOW = """
# Example workflow - run with: hivemind workflow example
[workflow.example]
name = "example"
steps = [
  "Summarize the project in one paragraph",
  "List key files and their purpose",
]
"""


def _run_init_interactive() -> tuple[str, bool, bool]:
    """
    Interactive flow: provider → planner/worker models → workers, memory, dataset, workflow.
    Returns (toml_content, create_dataset, create_workflow).
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, IntPrompt, Prompt

    console = Console()

    console.print()
    console.print(
        Panel(
            "[bold]Hivemind project setup[/]\n\n"
            "We'll create [cyan]hivemind.toml[/], optional example workflow, and a [cyan]dataset/[/] folder.",
            title="Welcome",
            border_style="green",
        )
    )
    console.print()

    choices = _provider_choices_for_display()
    provider_id = _select_option("Select model provider", choices, default_index=0)
    console.print(f"  [dim]Using provider: {provider_id}[/]\n")

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

    toml_content = _build_init_toml(
        workers=workers,
        planner=planner_model,
        worker=worker_model,
        memory_enabled=memory_enabled,
        tools_top_k=tools_top_k,
    )

    create_workflow = Confirm.ask("Add example workflow to hivemind.toml?", default=True)
    create_dataset = Confirm.ask("Create dataset/ folder?", default=True)

    return toml_content, create_dataset, create_workflow


def run_init(interactive: bool = True) -> int:
    """
    Set up a new project: create hivemind.toml, optional example workflow, dataset folder.
    When interactive=True, prompt for provider, models, workers, memory, and options.
    """
    cwd = Path.cwd()
    errors: list[str] = []

    created_toml = False
    created_workflow = False
    created_dataset = False
    toml_content: str
    add_workflow = True
    add_dataset = True

    toml_path = cwd / "hivemind.toml"
    if toml_path.exists():
        errors.append("hivemind.toml already exists")
    else:
        if interactive:
            try:
                toml_content, add_dataset, add_workflow = _run_init_interactive()
                if add_workflow:
                    toml_content = toml_content.strip() + EXAMPLE_WORKFLOW
            except (KeyboardInterrupt, EOFError):
                print("\nInit cancelled.", file=sys.stderr)
                return 130
        else:
            toml_content = _build_init_toml(
                workers=4,
                planner="auto",
                worker="auto",
                memory_enabled=True,
                tools_top_k=12,
            ).strip() + EXAMPLE_WORKFLOW
            add_workflow = True
            add_dataset = True

        try:
            toml_path.write_text(toml_content, encoding="utf-8")
            created_toml = True
            created_workflow = add_workflow and "[workflow.example]" in toml_content
        except Exception as e:
            errors.append(f"Failed to create hivemind.toml: {e}")

    if add_dataset:
        dataset_dir = cwd / "dataset"
        if not dataset_dir.exists():
            try:
                dataset_dir.mkdir(parents=True, exist_ok=True)
                (dataset_dir / ".gitkeep").write_text("", encoding="utf-8")
                created_dataset = True
            except Exception as e:
                errors.append(f"Failed to create dataset folder: {e}")

    env_ok = _check_env_quiet()

    from rich.console import Console

    console = Console()
    if created_toml:
        console.print("[green]✔[/] hivemind.toml created")
    if created_workflow:
        console.print("[green]✔[/] example workflow added")
    if created_dataset:
        console.print("[green]✔[/] dataset/ folder created")
    if env_ok:
        console.print("[green]✔[/] environment check passed")
    elif not errors and created_toml:
        console.print(
            "[yellow]⚠[/] No API keys detected. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GOOGLE_API_KEY, or GITHUB_TOKEN (see hivemind doctor)."
        )

    if errors:
        for e in errors:
            console.print(f"[red]✗[/] {e}", style="red")
        return 1

    console.print()
    console.print("Next steps:")
    console.print("  1) Set API keys (e.g. OPENAI_API_KEY) if not already set")
    console.print("  2) Edit hivemind.toml if needed")
    console.print('  3) Run: [cyan]hivemind run "your task"[/]')
    return 0


def _check_env_quiet() -> bool:
    """Return True if at least one provider env is set."""
    return bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or (os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"))
    )


def run_doctor() -> int:
    """
    Verify environment: GITHUB_TOKEN, OpenAI keys, config file, tool registry.
    """
    issues: list[str] = []
    ok: list[str] = []

    if os.environ.get("GITHUB_TOKEN"):
        ok.append("GITHUB_TOKEN is set")
    else:
        issues.append("GITHUB_TOKEN not set (optional, for GitHub Models)")

    if os.environ.get("OPENAI_API_KEY"):
        ok.append("OPENAI_API_KEY is set")
    else:
        issues.append("OPENAI_API_KEY not set (optional)")

    from hivemind.config.config_loader import project_config_paths

    found = False
    for p in project_config_paths():
        if p.is_file():
            ok.append(f"Config file found: {p}")
            found = True
            break
    if not found:
        issues.append("No project config (hivemind.toml or workflow.hivemind.toml) in cwd or parent")

    try:
        from hivemind.tools.registry import list_tools

        tools = list_tools()
        ok.append(f"Tool registry: {len(tools)} tools loaded")
    except Exception as e:
        issues.append(f"Tool registry: {e}")

    from rich.console import Console

    console = Console()
    for s in ok:
        console.print(f"[green]✔[/] {s}")
    for s in issues:
        console.print(f"[red]✗[/] {s}", style="red")
    return 0 if not issues else 1
