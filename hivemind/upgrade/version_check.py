"""
Version checking: PyPI latest version, cache, semver comparison.
"""

import json
from pathlib import Path
from typing import Literal

import httpx

PYPI_URL = "https://pypi.org/pypi/hivemind-ai/json"
CACHE_FILE = Path("~/.config/hivemind/update_check.json").expanduser()
CACHE_TTL_HOURS = 24
PACKAGE_NAME = "hivemind-ai"


def get_current_version() -> str:
    """Read current installed version from importlib.metadata."""
    import importlib.metadata

    return importlib.metadata.version(PACKAGE_NAME)


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.is_file():
        return False
    try:
        data = json.loads(CACHE_FILE.read_text())
        checked_at = data.get("checked_at", "")
        if not checked_at:
            return False
        from datetime import datetime, timezone

        # ISO format with Z
        dt = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - dt).total_seconds() / 3600
        return age_hours < CACHE_TTL_HOURS
    except (json.JSONDecodeError, ValueError, OSError):
        return False


def _read_cached_version() -> str | None:
    if not _cache_is_fresh():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        return data.get("latest")
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(latest: str) -> None:
    from datetime import datetime, timezone

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "latest": latest,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    CACHE_FILE.write_text(json.dumps(data, indent=2))
    try:
        CACHE_FILE.chmod(0o600)
    except OSError:
        pass


def get_latest_version() -> str:
    """
    Fetch latest version from PyPI with 24h cache.
    On network error, return current version (fail silently).
    """
    cached = _read_cached_version()
    if cached is not None:
        return cached
    try:
        resp = httpx.get(PYPI_URL, timeout=5.0)
        resp.raise_for_status()
        info = resp.json().get("info") or {}
        latest = info.get("version") or get_current_version()
        _write_cache(latest)
        return latest
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return get_current_version()


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse '1.2.3' or '1.2.3.post1' into (1, 2, 3)."""
    # Strip pre/post/dev suffixes for comparison
    base = version.split("+")[0].split("-")[0]
    parts = base.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return (major, minor, patch)


def get_version_diff_type(
    current: str, latest: str
) -> Literal["major", "minor", "patch"]:
    """Compare semver tuples; return highest changed segment."""
    c = parse_semver(current)
    l = parse_semver(latest)
    if l[0] != c[0]:
        return "major"
    if l[1] != c[1]:
        return "minor"
    return "patch"


def is_update_available() -> tuple[bool, str, str]:
    """
    Returns (available, current, latest).
    Uses cache for latest; on network error latest may equal current.
    """
    current = get_current_version()
    latest = get_latest_version()
    c = parse_semver(current)
    l = parse_semver(latest)
    available = (l[0], l[1], l[2]) > (c[0], c[1], c[2])
    return (available, current, latest)
