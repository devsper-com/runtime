"""
Installer detection (uv vs pip) and install execution.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

PACKAGE_NAME = "devsper"
INSTALL_TIMEOUT = 120


def detect_installer() -> Literal["uv", "pip"]:
    """
    Check in order: DEVSPER_INSTALLER env, uv-managed env, which uv, else pip.
    """
    env = os.environ.get("DEVSPER_INSTALLER", "").strip().lower()
    if env in ("uv", "pip"):
        return "uv" if env == "uv" else "pip"

    # Check if we're in a uv-managed environment
    cwd = Path.cwd()
    home = Path.home()
    while cwd != home and cwd != cwd.parent:
        if (cwd / ".python-version").exists() or (cwd / "uv.lock").exists():
            if shutil.which("uv"):
                return "uv"
            break
        cwd = cwd.parent
    if (home / ".python-version").exists() or (home / "uv.lock").exists():
        if shutil.which("uv"):
            return "uv"

    # sys.executable in .venv or /uv/ often indicates uv
    exe = sys.executable
    if "/uv/" in exe or ".venv" in exe:
        if shutil.which("uv"):
            return "uv"

    if shutil.which("uv"):
        return "uv"
    return "pip"


def get_install_command(
    installer: Literal["uv", "pip"],
    package: str = PACKAGE_NAME,
    version: str | None = None,
) -> list[str]:
    """Build the install command list."""
    spec = f"{package}=={version}" if version else package
    if installer == "uv":
        return ["uv", "pip", "install", "--upgrade", spec]
    return [sys.executable, "-m", "pip", "install", "--upgrade", spec]


def perform_install(
    installer: Literal["uv", "pip"], version: str | None = None
) -> tuple[bool, str]:
    """
    Run the install command. Returns (success, output).
    Timeout 120 seconds.
    """
    cmd = get_install_command(installer, version=version)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            return (False, out)
        return (True, out)
    except subprocess.TimeoutExpired:
        return (False, "Installation timed out after 120 seconds.")
    except Exception as e:
        return (False, str(e))


def verify_installation(expected_version: str) -> bool:
    """Run Python to get installed devsper version and compare to expected."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('devsper'))",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        actual = result.stdout.strip()
        return actual == expected_version
    except Exception:
        return False
