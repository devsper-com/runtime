from __future__ import annotations

import os
from typing import Any

from devsper.platform.request_builder import PlatformAPIError, PlatformAPIRequestBuilder


def fetch_org_policy() -> dict[str, Any]:
    api = PlatformAPIRequestBuilder()
    if not api.enabled():
        return {}
    try:
        data = api.get_json(f"/orgs/{api.org_slug}/policy", params=None)
        return (data or {}).get("policy") or {}
    except PlatformAPIError:
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
