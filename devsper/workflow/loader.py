"""Load workflow definitions from workflow.devsper.toml or devsper.toml."""

import secrets
import os
from pathlib import Path
from typing import Any

import tomllib
import requests

from devsper.workflow.schema import (
    OutputField,
    StepCondition,
    WorkflowDefinition,
    WorkflowStep,
)


def _find_workflow_file() -> Path | None:
    cwd = Path.cwd()
    for base in (cwd, cwd.parent):
        for name in ("workflow.devsper.toml", "devsper.toml"):
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


def _workflow_from_legacy_steps(steps: list[str]) -> WorkflowDefinition:
    """Wrap a list of task strings into a WorkflowDefinition with auto-generated step ids."""
    workflow_steps = []
    for i, task in enumerate(steps):
        step_id = f"step_{secrets.token_hex(3)}"
        workflow_steps.append(
            WorkflowStep(
                id=step_id,
                task=task,
                depends_on=[workflow_steps[-1].id] if workflow_steps else [],
            )
        )
    return WorkflowDefinition(
        name="legacy",
        description="Legacy workflow from list of steps",
        version="1.0",
        steps=workflow_steps,
        inputs=[],
    )


def _step_dict_to_model(d: dict[str, Any]) -> WorkflowStep:
    """Convert a raw step dict (from TOML) to WorkflowStep."""
    # TOML may have "if" as key; Pydantic expects alias "if" -> if_
    raw = dict(d)
    if "if" in raw and isinstance(raw["if"], dict):
        raw["if"] = StepCondition(expression=raw["if"].get("expression", ""))
    elif "if" in raw and isinstance(raw["if"], str):
        raw["if"] = StepCondition(expression=raw["if"])
    if "output_schema" in raw and isinstance(raw["output_schema"], list):
        raw["output_schema"] = [
            OutputField(**f) if isinstance(f, dict) else f for f in raw["output_schema"]
        ]
    return WorkflowStep(**raw)


def _workflow_dict_to_definition(name: str, raw: dict[str, Any]) -> WorkflowDefinition:
    """Convert raw workflow dict to WorkflowDefinition."""
    steps_raw = raw.get("steps") or []
    if not steps_raw:
        return WorkflowDefinition(
            name=name,
            description=raw.get("description"),
            version=str(raw.get("version", "1.0")),
            steps=[],
            inputs=raw.get("inputs") or [],
        )
    # Legacy: list of strings
    if all(isinstance(s, str) for s in steps_raw):
        wf = _workflow_from_legacy_steps(steps_raw)
        wf = WorkflowDefinition(
            name=name,
            description=raw.get("description") or wf.description,
            version=str(raw.get("version", "1.0")),
            steps=wf.steps,
            inputs=raw.get("inputs") or [],
        )
        return wf
    # New format: list of step dicts
    steps = []
    for s in steps_raw:
        if isinstance(s, dict):
            steps.append(_step_dict_to_model(s))
        else:
            steps.append(s)
    inputs_raw = raw.get("inputs") or []
    inputs = [OutputField(**f) if isinstance(f, dict) else f for f in inputs_raw]
    return WorkflowDefinition(
        name=name,
        description=raw.get("description"),
        version=str(raw.get("version", "1.0")),
        steps=steps,
        inputs=inputs,
    )


def load_workflow(name: str, config_path: Path | None = None) -> WorkflowDefinition | None:
    """
    Load workflow by name. Returns WorkflowDefinition (Pydantic model).
    If config_path is given, read that file; else discover workflow.devsper.toml / devsper.toml.
    Legacy: if steps are a list of strings, they are wrapped in a WorkflowDefinition with
    auto-generated step ids and sequential dependencies.
    """
    remote = _load_remote_workflow(name)
    if remote is not None:
        return remote
    path = config_path or _find_workflow_file()
    if not path:
        return None
    data = _load_toml(path)
    raw: dict[str, Any] | None = None
    # Single [workflow] section
    wf = data.get("workflow")
    if isinstance(wf, dict) and wf.get("name") == name:
        raw = {"name": name, **wf}
    if raw is None:
        for key, val in data.items():
            if key.startswith("workflow.") and isinstance(val, dict):
                if val.get("name") == name or key == f"workflow.{name}":
                    raw = {"name": name, **val}
                    break
    if not raw:
        return None
    return _workflow_dict_to_definition(name, raw)


def _load_remote_workflow(name: str) -> WorkflowDefinition | None:
    if "@" not in name or "/" not in name:
        return None
    base = os.environ.get("DEVSPER_PLATFORM_API_URL", "").rstrip("/")
    org = os.environ.get("DEVSPER_PLATFORM_ORG", "")
    token = os.environ.get("DEVSPER_PLATFORM_TOKEN", "")
    if not base or not org:
        return None
    wf_name, version = name.split("@", 1)
    wf_name = wf_name.split("/", 1)[-1]
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        version_num = int(version)
    except Exception:
        return None
    try:
        resp = requests.get(
            f"{base}/orgs/{org}/workflow-specs/{wf_name}/versions/{version_num}",
            headers=headers,
            timeout=15,
        )
        if not resp.ok:
            return None
        data = resp.json() or {}
        spec = data.get("spec")
        if not isinstance(spec, dict):
            return None
        return _workflow_dict_to_definition(
            wf_name,
            {
                "description": spec.get("description") or "remote workflow",
                "version": str(data.get("version") or version_num),
                "steps": spec.get("steps") or [],
                "inputs": spec.get("inputs") or [],
            },
        )
    except Exception:
        return None


def list_workflows(config_path: Path | None = None) -> list[str]:
    """Return list of workflow identifiers (name or key suffix) that load_workflow() accepts."""
    path = config_path or _find_workflow_file()
    if not path:
        return []
    data = _load_toml(path)
    names: list[str] = []
    wf = data.get("workflow")
    if isinstance(wf, dict) and wf.get("name"):
        names.append(str(wf["name"]))
    for key, val in data.items():
        if key.startswith("workflow.") and isinstance(val, dict):
            # Use key suffix so load_workflow(key_suffix) works
            key_suffix = key.removeprefix("workflow.")
            if key_suffix and key_suffix not in names:
                names.append(key_suffix)
    return list(dict.fromkeys(names))
