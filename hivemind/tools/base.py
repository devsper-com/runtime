"""
Base tool interface for the Hivemind tool system.

All tools are stateless and must return strings so agents can parse the output.
"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for all Hivemind tools.

    Tools are stateless. They accept keyword arguments matching input_schema
    and return a string result for the agent to consume.
    """

    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool with the given arguments. Returns a string result."""
        ...
