"""
Base tool interface for the devsper tool system.

All tools are stateless and must return strings so agents can parse the output.
"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """
    Base class for all devsper tools.

    Tools are stateless. They accept keyword arguments matching input_schema
    and return a string result for the agent to consume.

    category: optional label for filtering (e.g. "research", "coding", "documents").
    If unset, the tool selector may infer from the tool's module path.
    """

    name: str = ""
    description: str = ""
    input_schema: dict = {}
    category: str = ""

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool with the given arguments. Returns a string result."""
        ...
