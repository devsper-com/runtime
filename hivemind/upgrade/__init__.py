"""
Upgrade module: check for updates, changelog, installer detection, perform upgrade.
"""

from .version_check import (
    is_update_available,
    get_current_version,
    get_latest_version,
)
from .installer import detect_installer, perform_install
from .changelog import fetch_changelog, get_changes_between

__all__ = [
    "is_update_available",
    "get_current_version",
    "get_latest_version",
    "detect_installer",
    "perform_install",
    "fetch_changelog",
    "get_changes_between",
]
