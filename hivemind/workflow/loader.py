"""Load workflow definitions from workflow.hivemind.toml or hivemind.toml."""

from pathlib import Path

import tomllib


def _find_workflow_file() -> Path | None:
    cwd = Path.cwd()
    for base in (cwd, cwd.parent):
        for name in ("workflow.hivemind.toml", "hivemind.toml"):
            p = base / name
            if p.is_file():
                return p
    return None


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def load_workflow(name: str, config_path: Path | None = None) -> dict | None:
    """
    Load workflow by name. Returns dict with "name" and "steps" (list of step descriptions).
    If config_path is given, read that file; else discover workflow.hivemind.toml / hivemind.toml.
    """
    path = config_path or _find_workflow_file()
    if not path:
        return None
    data = _load_toml(path)
    # Single [workflow] section
    wf = data.get("workflow")
    if isinstance(wf, dict) and wf.get("name") == name:
        return {"name": name, "steps": wf.get("steps") or []}
    # Multiple workflows: [workflow.name]
    for key, val in data.items():
        if key.startswith("workflow.") and isinstance(val, dict):
            if val.get("name") == name or key == f"workflow.{name}":
                return {"name": name, "steps": val.get("steps") or []}
    return None


def list_workflows(config_path: Path | None = None) -> list[str]:
    """Return list of workflow names defined in the config file."""
    path = config_path or _find_workflow_file()
    if not path:
        return []
    data = _load_toml(path)
    names: list[str] = []
    wf = data.get("workflow")
    if isinstance(wf, dict) and wf.get("name"):
        names.append(str(wf["name"]))
    for key, val in data.items():
        if key.startswith("workflow.") and isinstance(val, dict) and val.get("name"):
            names.append(str(val["name"]))
    return list(dict.fromkeys(names))
