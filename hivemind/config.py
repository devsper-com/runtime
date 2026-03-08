"""
Unified configuration: TOML in ~/.config/hivemind (and optional .hivemind/config.toml)
with env overrides. Provider config (endpoints, api_key, deployment_name) can live
in TOML so hivemind works from any directory; values are applied to os.environ when
not already set so existing provider code keeps working.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import tomllib

_PROVIDER_ENV = {
    "azure_openai": [
        ("endpoint", "AZURE_OPENAI_ENDPOINT"),
        ("api_key", "AZURE_OPENAI_API_KEY"),
        ("deployment_name", "AZURE_OPENAI_DEPLOYMENT_NAME"),
        ("api_version", "AZURE_OPENAI_API_VERSION"),
    ],
    "azure_anthropic": [
        ("endpoint", "AZURE_ANTHROPIC_ENDPOINT"),
        ("api_key", "AZURE_ANTHROPIC_API_KEY"),
        ("deployment_name", "AZURE_ANTHROPIC_DEPLOYMENT_NAME"),
    ],
    "openai": [("api_key", "OPENAI_API_KEY")],
    "anthropic": [("api_key", "ANTHROPIC_API_KEY")],
    "google": [("api_key", "GOOGLE_API_KEY")],
}


def _user_config_path() -> Path:
    return Path.home() / ".config" / "hivemind" / "config.toml"


def _project_config_path() -> Path | None:
    """Project override: .hivemind/config.toml from cwd or parent (project root)."""
    cwd = Path.cwd()
    for base in (cwd, cwd.parent):
        p = base / ".hivemind" / "config.toml"
        if p.is_file():
            return p
    return None


def _infer_worker_model_from_env() -> str:
    """Infer worker model from API keys when not set in config (mirror examples/_config.py)."""
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        return "gpt-5-mini"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get("AZURE_ANTHROPIC_API_KEY"):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


def _infer_planner_model_from_env() -> str:
    """Infer planner model from API keys when not set in config."""
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        return "gpt-4o"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get("AZURE_ANTHROPIC_API_KEY"):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


@dataclass(frozen=True)
class HivemindConfig:
    """Resolved config: env overrides > project TOML > user TOML > defaults."""

    worker_model: str
    planner_model: str
    events_dir: str
    data_dir: str

    @classmethod
    def default(cls) -> "HivemindConfig":
        return cls(
            worker_model=_infer_worker_model_from_env(),
            planner_model=_infer_planner_model_from_env(),
            events_dir=".hivemind/events",
            data_dir=".hivemind",
        )


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _get_str(data: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        if key in data and isinstance(data[key], str):
            return data[key]
    return default


def _apply_provider_toml_to_env(toml_data: dict) -> None:
    """Apply [azure_openai], [azure_anthropic], etc. to os.environ when not already set."""
    for section, mappings in _PROVIDER_ENV.items():
        block = toml_data.get(section)
        if not isinstance(block, dict):
            continue
        for toml_key, env_key in mappings:
            val = block.get(toml_key)
            if val is not None and str(val).strip() and env_key not in os.environ:
                os.environ[env_key] = str(val).strip()


def get_config() -> HivemindConfig:
    """
    Load config: env overrides > .hivemind/config.toml > ~/.config/hivemind/config.toml > defaults.
    Provider sections in TOML ([azure_openai], [azure_anthropic], etc.) are applied to os.environ
    when not set, so hivemind works from any directory without loading .env.
    """
    user_path = _user_config_path()
    user = _load_toml(user_path)
    _apply_provider_toml_to_env(user) 
    user_default = user.get("default") if isinstance(user.get("default"), dict) else {}
    if not user_default:
        user_default = {k: v for k, v in user.items() if isinstance(v, (str, int, float, bool))}  # allow [default] or top-level keys

    project_path = _project_config_path()
    project = _load_toml(project_path) if project_path else {}
    _apply_provider_toml_to_env(project)
    proj_default = project.get("default") if isinstance(project.get("default"), dict) else {}
    if not proj_default:
        proj_default = {k: v for k, v in project.items() if isinstance(v, (str, int, float, bool))}

    # precedence: defaults → user TOML → project TOML → env
    worker_model = _infer_worker_model_from_env()
    planner_model = _infer_planner_model_from_env()
    events_dir = ".hivemind/events"
    data_dir = ".hivemind"

    worker_model = _get_str(user_default, "worker_model") or worker_model
    planner_model = _get_str(user_default, "planner_model") or planner_model
    events_dir = _get_str(user_default, "events_dir") or events_dir
    data_dir = _get_str(user_default, "data_dir") or data_dir

    worker_model = _get_str(proj_default, "worker_model") or worker_model
    planner_model = _get_str(proj_default, "planner_model") or planner_model
    events_dir = _get_str(proj_default, "events_dir") or events_dir
    data_dir = _get_str(proj_default, "data_dir") or data_dir

    if os.environ.get("HIVEMIND_WORKER_MODEL"):
        worker_model = os.environ["HIVEMIND_WORKER_MODEL"]
    if os.environ.get("HIVEMIND_PLANNER_MODEL"):
        planner_model = os.environ["HIVEMIND_PLANNER_MODEL"]
    if os.environ.get("HIVEMIND_EVENTS_DIR"):
        events_dir = os.environ["HIVEMIND_EVENTS_DIR"]
    if os.environ.get("HIVEMIND_DATA_DIR"):
        data_dir = os.environ["HIVEMIND_DATA_DIR"]

    return HivemindConfig(
        worker_model=worker_model,
        planner_model=planner_model,
        events_dir=events_dir,
        data_dir=data_dir,
    )
