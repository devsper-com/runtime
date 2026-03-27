from __future__ import annotations

from datetime import datetime, timezone


def build_manifest(
    *,
    name: str,
    devsper_version: str,
    agents: list[dict],
    tools_required: list[str],
    models_required: list[str],
    avg_cost_per_run_usd: float = 0.0,
    avg_duration_s: float = 0.0,
    description: str = "",
    author: str = "",
) -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "description": description,
        "devsper_version": devsper_version,
        "agents": agents,
        "tools_required": sorted(set(tools_required)),
        "models_required": sorted(set(models_required)),
        "avg_cost_per_run_usd": float(avg_cost_per_run_usd),
        "avg_duration_s": float(avg_duration_s),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "author": author,
    }
