"""
devsper: distributed AI swarm runtime.

Example:
    from devsper import Swarm

    swarm = Swarm(config="devsper.toml")
    result = swarm.run("analyze diffusion models")
"""

try:
    from importlib.metadata import version as _package_version
except ImportError:  # pragma: no cover
    _package_version = None  # type: ignore[misc, assignment]

try:
    __version__ = _package_version("devsper") if _package_version else "0.0.0"
except Exception:  # pragma: no cover - missing dist metadata (e.g. bare checkout)
    __version__ = "0.0.0"

from devsper.config import get_config

__all__ = ["Swarm", "get_config", "__version__"]


def __getattr__(name: str):
    # Keep package import lightweight for tooling/tests.
    if name == "Swarm":
        from devsper.swarm.swarm import Swarm  # local import

        return Swarm
    raise AttributeError(name)
