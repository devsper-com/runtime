"""
Hivemind: distributed AI swarm runtime.

Example:
    from hivemind import Swarm

    swarm = Swarm(config="hivemind.toml")
    result = swarm.run("analyze diffusion models")
"""

from hivemind.config import get_config
from hivemind.swarm.swarm import Swarm

__all__ = ["Swarm", "get_config"]
