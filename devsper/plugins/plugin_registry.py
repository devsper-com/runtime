"""Registry of loaded plugins: name, version, tools registered."""

from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    name: str
    version: str = ""
    tools_registered: list[str] = field(default_factory=list)


_plugins: dict[str, PluginInfo] = {}


def register_plugin(name: str, version: str = "", tools: list[str] | None = None) -> None:
    _plugins[name] = PluginInfo(
        name=name,
        version=version,
        tools_registered=list(tools or []),
    )


def get_plugin(name: str) -> PluginInfo | None:
    return _plugins.get(name)


def list_plugins() -> list[PluginInfo]:
    return list(_plugins.values())


def clear_plugins() -> None:
    """Clear registry (mainly for tests)."""
    _plugins.clear()
