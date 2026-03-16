"""Discover and load plugins via entry_points (devsper.plugins)."""

import importlib.metadata
import logging
from devsper.tools.base import Tool
from devsper.tools.registry import register

from devsper.plugins.plugin_registry import register_plugin

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "devsper.plugins"


def _load_entry_points(group: str = ENTRY_POINT_GROUP):
    try:
        eps = importlib.metadata.entry_points(group=group)
    except TypeError:
        eps = importlib.metadata.entry_points().get(group, [])
    return list(eps)


def _invoke_plugin(ep: importlib.metadata.EntryPoint) -> list[str]:
    """
    Load entry point and register tools. Entry point can be:
    - A callable that returns a list of Tool instances
    - A callable that takes no args and calls register() itself (returns None or list of tool names)
    Returns list of tool names registered.
    """
    try:
        fn = ep.load()
    except Exception as e:
        logger.warning("Plugin %s failed to load: %s", ep.name, e)
        return []
    registered: list[str] = []
    try:
        result = fn()
        if result is None:
            return registered
        if isinstance(result, list):
            for item in result:
                if isinstance(item, Tool):
                    register(item)
                    registered.append(item.name)
                elif isinstance(item, str):
                    registered.append(item)
    except Exception as e:
        logger.warning("Plugin %s failed to run: %s", ep.name, e)
    return registered


def load_plugins(enabled: list[str] | None = None) -> list[str]:
    """
    Discover plugins from entry_points and register their tools.
    If enabled is provided, only load those plugin names; otherwise load all.
    Returns list of plugin names that were loaded.
    """
    loaded: list[str] = []
    for ep in _load_entry_points():
        if enabled is not None and ep.name not in enabled:
            continue
        try:
            dist = ep.dist
            version = dist.version if dist else ""
        except Exception:
            version = ""
        tool_names = _invoke_plugin(ep)
        register_plugin(ep.name, version=version, tools=tool_names)
        loaded.append(ep.name)
    return loaded
