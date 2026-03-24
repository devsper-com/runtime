from __future__ import annotations

import os
from typing import Any

import requests


def fetch_org_policy() -> dict[str, Any]:
    base = os.environ.get("DEVSPER_PLATFORM_API_URL", "").rstrip("/")
    org = os.environ.get("DEVSPER_PLATFORM_ORG", "")
    token = os.environ.get("DEVSPER_PLATFORM_TOKEN", "")
    if not base or not org:
        return {}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.get(f"{base}/orgs/{org}/policy", headers=headers, timeout=10)
        if not resp.ok:
            return {}
        return (resp.json() or {}).get("policy") or {}
    except Exception:
        return {}


def enforce_model_policy(model: str) -> None:
    policy = fetch_org_policy()
    allowed = policy.get("allowed_models") if isinstance(policy, dict) else None
    if isinstance(allowed, list) and allowed and model not in allowed:
        raise PermissionError(f"Model '{model}' is blocked by org policy")


def filter_tools_by_policy(tool_names: list[str]) -> list[str]:
    policy = fetch_org_policy()
    blocked = set(policy.get("blocked_tools") or []) if isinstance(policy, dict) else set()
    if not blocked:
        return tool_names
    return [t for t in tool_names if t not in blocked]
