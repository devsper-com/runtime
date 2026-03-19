"""
devsper: distributed AI swarm runtime.

Example:
    from devsper import Swarm

    swarm = Swarm(config="devsper.toml")
    result = swarm.run("analyze diffusion models")
"""

from devsper.config import get_config

__all__ = ["Swarm", "get_config"]


def __getattr__(name: str):
    # Keep package import lightweight for tooling/tests.
    if name == "Swarm":
        from devsper.swarm.swarm import Swarm  # local import

        return Swarm
    raise AttributeError(name)
