"""Plugin system: discover and load tools via entry_points."""

from hivemind.plugins.plugin_loader import load_plugins
from hivemind.plugins.plugin_registry import (
    PluginInfo,
    clear_plugins,
    get_plugin,
    list_plugins,
    register_plugin,
)

__all__ = [
    "load_plugins",
    "PluginInfo",
    "register_plugin",
    "get_plugin",
    "list_plugins",
    "clear_plugins",
]
