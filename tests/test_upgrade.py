"""Tests for devsper upgrade module (version check, changelog, installer, notifier)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from devsper.upgrade.version_check import (
    get_current_version,
    get_latest_version,
    is_update_available,
    parse_semver,
    get_version_diff_type,
    CACHE_FILE,
)
from devsper.upgrade.changelog import (
    parse_changelog,
    get_changes_between,
    format_changelog_rich,
)
from devsper.upgrade.installer import detect_installer, get_install_command
from devsper.upgrade.notifier import check_and_notify, suppress_notifications


# ---------------------------------------------------------------------------
# version_check
# ---------------------------------------------------------------------------


def test_parse_semver():
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert parse_semver("0.1.0") == (0, 1, 0)
    assert parse_semver("1.2.3.post1") == (1, 2, 3)
    assert parse_semver("2.0.0") == (2, 0, 0)


def test_get_version_diff_type():
    assert get_version_diff_type("1.2.3", "2.0.0") == "major"
    assert get_version_diff_type("1.2.3", "1.3.0") == "minor"
    assert get_version_diff_type("1.2.3", "1.2.4") == "patch"


def test_get_current_version():
    v = get_current_version()
    assert v and len(v) >= 5  # e.g. 1.1.1
    parts = v.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() or not p for p in parts[:3])


def test_version_check_cache(tmp_path):
    """Cache is used when file exists and is within TTL."""
    cache = tmp_path / "update_check.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "latest": "99.99.99",
                "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    )
    with patch("devsper.upgrade.version_check.CACHE_FILE", cache):
        latest = get_latest_version()
        assert latest == "99.99.99"


def test_version_check_fetch_and_cache(tmp_path):
    """When cache miss, fetch PyPI and write cache."""
    cache = tmp_path / "update_check.json"
    # No cache file or stale: so fetch will run
    with patch("devsper.upgrade.version_check.CACHE_FILE", cache):
        with patch("httpx.get") as mget:
            mget.return_value.json.return_value = {
                "info": {"version": "1.2.3"},
            }
            mget.return_value.raise_for_status = MagicMock()
            latest = get_latest_version()
            assert latest == "1.2.3"
            assert cache.exists()
            data = json.loads(cache.read_text())
            assert data["latest"] == "1.2.3"
            assert "checked_at" in data


# ---------------------------------------------------------------------------
# installer
# ---------------------------------------------------------------------------


def test_detect_installer_uv():
    """When uv is on PATH, detect uv."""
    with patch("shutil.which", return_value="/usr/bin/uv"):
        with patch.dict("os.environ", {"DEVSPER_INSTALLER": ""}, clear=False):
            result = detect_installer()
            assert result == "uv"


def test_detect_installer_env_override():
    """DEVSPER_INSTALLER=pip overrides uv detection."""
    with patch("shutil.which", return_value="/usr/bin/uv"):
        with patch.dict("os.environ", {"DEVSPER_INSTALLER": "pip"}):
            assert detect_installer() == "pip"
    with patch.dict("os.environ", {"DEVSPER_INSTALLER": "uv"}):
        with patch("shutil.which", return_value=None):
            assert detect_installer() == "uv"


def test_get_install_command():
    cmd_uv = get_install_command("uv", version="1.2.3")
    assert cmd_uv == ["uv", "pip", "install", "--upgrade", "devsper==1.2.3"]
    cmd_pip = get_install_command("pip", version="1.2.3")
    assert cmd_pip[0].endswith("python") or "python" in cmd_pip[0]
    assert "-m" in cmd_pip and "pip" in cmd_pip and "install" in cmd_pip
    assert "devsper==1.2.3" in cmd_pip


# ---------------------------------------------------------------------------
# changelog
# ---------------------------------------------------------------------------

SAMPLE_CHANGELOG = """
# Changelog

## [1.3.0] - 2026-04-01

### Added
- New feature A
- New feature B

### Changed
- Improved X

## [1.2.1] - 2026-03-15

### Fixed
- Bug fix 1

## [1.2.0] - 2026-03-10

### Added
- Feature Y
"""


def test_changelog_parser():
    """Parse CHANGELOG.md and assert correct version sections."""
    parsed = parse_changelog(SAMPLE_CHANGELOG)
    assert "1.3.0" in parsed
    assert "1.2.1" in parsed
    assert "1.2.0" in parsed
    assert "New feature A" in parsed["1.3.0"]
    assert "Bug fix 1" in parsed["1.2.1"]
    assert "Feature Y" in parsed["1.2.0"]


def test_get_changes_between():
    """Only versions between current (exclusive) and latest (inclusive) are returned."""
    parsed = parse_changelog(SAMPLE_CHANGELOG)
    changes = get_changes_between(parsed, "1.2.0", "1.3.0")
    versions = [c["version"] for c in changes]
    assert "1.2.0" not in versions
    assert "1.2.1" in versions
    assert "1.3.0" in versions
    # Newest first
    assert changes[0]["version"] == "1.3.0"
    assert changes[-1]["version"] == "1.2.1"
    for c in changes:
        assert c["type"] in ("major", "minor", "patch")
        assert "notes" in c


def test_format_changelog_rich():
    changes = [
        {"version": "1.3.0", "notes": "- Feature A\n- Feature B", "type": "minor"},
        {"version": "1.2.1", "notes": "- Fix", "type": "patch"},
    ]
    out = format_changelog_rich(changes)
    assert "1.3.0" in out
    assert "1.2.1" in out
    assert "Feature A" in out or "•" in out


# ---------------------------------------------------------------------------
# notifier
# ---------------------------------------------------------------------------


def test_notifier_no_block():
    """check_and_notify() completes in < 200ms with mocked cache."""
    import time

    with patch("devsper.upgrade.version_check.is_update_available", return_value=(False, "1.0.0", "1.0.0")):
        t0 = time.perf_counter()
        check_and_notify()
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 200


def test_no_update_available():
    """When on latest version, notifier does not print."""
    with patch("devsper.upgrade.notifier._console") as mcon:
        with patch("devsper.upgrade.version_check.is_update_available", return_value=(False, "1.1.1", "1.1.1")):
            check_and_notify()
            mcon.print.assert_not_called()


def test_suppress_notifications():
    """suppress_notifications() prevents the nag from showing."""
    import devsper.upgrade.notifier as notifier_mod

    suppress_notifications()
    try:
        with patch("devsper.upgrade.version_check.is_update_available", return_value=(True, "1.0.0", "2.0.0")):
            with patch("devsper.upgrade.notifier._console") as mcon:
                check_and_notify()
                mcon.print.assert_not_called()
    finally:
        notifier_mod._suppress = False
