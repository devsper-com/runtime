"""
devsper: distributed AI swarm runtime.

Example:
    from devsper import Swarm

    swarm = Swarm(config="devsper.toml")
    result = swarm.run("analyze diffusion models")
"""

from devsper.config import get_config
from devsper.swarm.swarm import Swarm

__all__ = ["Swarm", "get_config"]
