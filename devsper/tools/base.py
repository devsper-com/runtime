"""
Base tool interface for the devsper tool system.

All tools are stateless and must return strings so agents can parse the output.
"""

from abc import ABC, abstractmethod


class ToolError(Exception):
    """Raised when a tool cannot be executed (missing deps, credentials, etc.)."""


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


class ToolStub(Tool):
    """
    Placeholder for a tool that exists in the registry but cannot be instantiated
    on this worker (e.g. tool requires credentials or optional dependencies).
    """

    def __init__(self, name: str, description: str, category: str, input_schema: dict):
        self.name = name
        self.description = description
        self.category = category
        self.input_schema = input_schema

    def run(self, **kwargs) -> str:
        raise ToolError(
            f"Tool '{self.name}' is not available on this worker. "
            "It may require credentials or dependencies not installed here."
        )
