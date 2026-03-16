"""Exceptions for devsper types and bus."""


class EventSerializationError(Exception):
    """Raised when an event payload is not JSON-serializable."""


class TaskNotFoundError(Exception):
    """Raised when a task ID is not found in the scheduler."""


class BusConnectionError(Exception):
    """Raised when the message bus backend cannot connect (e.g. Redis unreachable)."""


class CheckpointNotFoundError(Exception):
    """Raised when a checkpoint file for a run_id is not found."""


class MCPToolError(Exception):
    """Raised when an MCP tools/call returns an error or invalid response."""
