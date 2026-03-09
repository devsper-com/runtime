"""
Changelog fetching and parsing: raw CHANGELOG.md, version sections, Rich formatting.
"""

import re
from typing import Literal

import httpx

from .version_check import get_version_diff_type, parse_semver

# Adjust org/repo if needed (e.g. for forks)
CHANGELOG_URL = "https://raw.githubusercontent.com/anthropic/hivemind/main/CHANGELOG.md"
MAX_LINES_PER_VERSION = 8


def fetch_changelog() -> str | None:
    """Fetch raw CHANGELOG.md content; return None on failure."""
    try:
        resp = httpx.get(CHANGELOG_URL, timeout=10.0)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError:
        return None


# Match ## [1.2.3], ## [1.2.3] - date, ## 1.2.3, ## 1.2.3 - date
_VERSION_HEADER = re.compile(
    r"^##\s+\[?(?P<version>\d+\.\d+\.\d+)\]?(?:\s*-\s*[^\n]*)?\s*$", re.MULTILINE
)


def parse_changelog(content: str) -> dict[str, str]:
    """
    Parse markdown changelog into {"1.2.3": "release notes text", ...}.
    Sections start with ## [1.2.3] or ## 1.2.3.
    """
    out: dict[str, str] = {}
    matches = list(_VERSION_HEADER.finditer(content))
    for i, m in enumerate(matches):
        version = m.group("version")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end].strip()
        # Normalize: drop leading/trailing blank lines, keep structure
        out[version] = block
    return out


def _version_in_range(v: str, current: str, latest: str) -> bool:
    """True if v is strictly after current and <= latest (by semver)."""
    cur = parse_semver(current)
    lat = parse_semver(latest)
    v_tup = parse_semver(v)
    if v_tup <= cur:
        return False
    if v_tup > lat:
        return False
    return True


def get_changes_between(
    changelog: dict[str, str], current: str, latest: str
) -> list[dict]:
    """
    Return list of {"version": "1.2.3", "notes": "...", "type": "major|minor|patch"}
    for all versions between current (exclusive) and latest (inclusive).
    Type is the bump from the previous release to this one. Sorted newest-first.
    """
    cur_tup = parse_semver(current)
    lat_tup = parse_semver(latest)
    if lat_tup <= cur_tup:
        return []

    candidates = [
        (ver, notes)
        for ver, notes in changelog.items()
        if _version_in_range(ver, current, latest)
    ]
    # Sort oldest first so we can compute "previous" for each
    candidates.sort(key=lambda x: parse_semver(x[0]))
    result: list[dict] = []
    prev = current
    for ver, notes in candidates:
        diff_type: Literal["major", "minor", "patch"] = get_version_diff_type(
            prev, ver
        )
        result.append({"version": ver, "notes": notes, "type": diff_type})
        prev = ver
    result.reverse()  # newest first
    return result


def format_changelog_rich(changes: list[dict]) -> str:
    """
    Format for terminal with Rich markup.
    Major: [bold red], minor: [bold yellow], patch: [bold green].
    Max MAX_LINES_PER_VERSION lines per version, then "... and N more changes".
    """
    lines: list[str] = []
    for entry in changes:
        ver = entry["version"]
        notes = entry["notes"]
        t = entry["type"]
        if t == "major":
            header = f"[bold red]Version {ver}[/bold red]"
        elif t == "minor":
            header = f"[bold yellow]Version {ver}[/bold yellow]"
        else:
            header = f"[bold green]Version {ver}[/bold green]"
        lines.append(header)
        note_lines = [ln.strip() for ln in notes.splitlines() if ln.strip()]
        # Skip sub-headers like "### Added" when counting bullets; treat as structure
        bullet_lines = [ln for ln in note_lines if re.match(r"^[-*]|\d+\.", ln)]
        if not bullet_lines:
            bullet_lines = note_lines[:MAX_LINES_PER_VERSION]
        shown = bullet_lines[:MAX_LINES_PER_VERSION]
        for ln in shown:
            lines.append(f"  • {ln}" if not ln.startswith("•") else f"  {ln}")
        remaining = len(bullet_lines) - len(shown)
        if remaining > 0:
            lines.append(f"  [dim]... and {remaining} more changes[/dim]")
        lines.append("")
    return "\n".join(lines).strip()
