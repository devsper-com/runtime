"""Discover and load TOML config from standard locations."""

from pathlib import Path

import tomllib


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def user_config_path() -> Path:
    return Path.home() / ".config" / "hivemind" / "config.toml"


def project_config_paths() -> list[Path]:
    """Return candidate project config paths in order: hivemind.toml, workflow.hivemind.toml, .hivemind/config.toml (legacy)."""
    cwd = Path.cwd()
    paths = [
        cwd / "hivemind.toml",
        cwd / "workflow.hivemind.toml",
        cwd / ".hivemind" / "config.toml",
        cwd.parent / "hivemind.toml",
        cwd.parent / "workflow.hivemind.toml",
        cwd.parent / ".hivemind" / "config.toml",
    ]
    return paths


def load_user_config() -> dict:
    return _load_toml(user_config_path())


def load_project_config() -> dict:
    """Load first existing project config file (priority: hivemind.toml > workflow.hivemind.toml > .hivemind/config.toml)."""
    for p in project_config_paths():
        data = _load_toml(p)
        if data:
            return data
    return {}


def _extract_legacy_defaults(data: dict) -> dict:
    """Map legacy [default] or top-level keys into a flat dict for merging."""
    out: dict = {}
    default_block = data.get("default")
    if isinstance(default_block, dict):
        out = dict(default_block)
    # Top-level string/int/float/bool keys (legacy)
    for k, v in data.items():
        if k in ("default", "workflow", "swarm", "models", "memory", "tools", "telemetry", "providers"):
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
    return out


def normalize_toml_to_flat(data: dict) -> dict:
    """
    Normalize TOML data into a structure the resolver expects.
    Supports new format [swarm], [models], etc. and legacy [default] / top-level.
    """
    result: dict = {}
    legacy = _extract_legacy_defaults(data)
    if legacy:
        result["events_dir"] = legacy.get("events_dir", "")
        result["data_dir"] = legacy.get("data_dir", "")
        result["worker_model"] = legacy.get("worker_model", "")
        result["planner_model"] = legacy.get("planner_model", "")

    if "swarm" in data and isinstance(data["swarm"], dict):
        result["swarm"] = data["swarm"]
    if "models" in data and isinstance(data["models"], dict):
        result["models"] = data["models"]
    elif legacy:
        if legacy.get("worker_model"):
            result.setdefault("models", {})["worker"] = legacy["worker_model"]
        if legacy.get("planner_model"):
            result.setdefault("models", {})["planner"] = legacy["planner_model"]
    if "memory" in data and isinstance(data["memory"], dict):
        result["memory"] = data["memory"]
    if "tools" in data and isinstance(data["tools"], dict):
        result["tools"] = data["tools"]
    if "telemetry" in data and isinstance(data["telemetry"], dict):
        result["telemetry"] = data["telemetry"]
    if "providers" in data and isinstance(data["providers"], dict):
        result["providers"] = data["providers"]
    return result
