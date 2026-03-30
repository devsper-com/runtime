from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Iterable


def safe_import_modules(package_name: str) -> list[ModuleType]:
    """Import all submodules in a package; skip failures."""
    imported: list[ModuleType] = []
    try:
        pkg = importlib.import_module(package_name)
    except Exception:
        return imported

    imported.append(pkg)
    pkg_path = getattr(pkg, "__path__", None)
    if pkg_path is None:
        return imported

    prefix = package_name + "."
    for mod in pkgutil.walk_packages(pkg_path, prefix):
        try:
            imported.append(importlib.import_module(mod.name))
        except Exception:
            continue
    return imported


def bootstrap_tool_packages(packages: Iterable[str]) -> None:
    """Best-effort module loading for registration side effects."""
    for package in packages:
        safe_import_modules(package)

