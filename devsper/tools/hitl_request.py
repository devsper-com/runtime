"""
Synthetic HITL tool schema used for deterministic clarification requests.

The agent runtime intercepts `hitl.request` tool calls and routes them through
the clarification requester, so this tool is primarily for discoverability and
schema visibility in prompts.
"""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class HITLRequestTool(Tool):
    name = "hitl.request"
    description = (
        "Request required user clarification with structured fields. "
        "Use this instead of asking free-form questions."
    )
    category = "system"
    input_schema = {
        "type": "object",
        "required": ["context", "fields"],
        "properties": {
            "context": {"type": "string"},
            "priority": {"type": "integer"},
            "timeout_seconds": {"type": "integer"},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["type", "question"],
                    "properties": {
                        "type": {"type": "string"},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "default": {"type": "string"},
                        "required": {"type": "boolean"},
                    },
                },
            },
        },
    }

    def run(self, **kwargs) -> str:
        _ = kwargs
        return (
            "hitl.request must be handled by the agent runtime clarification "
            "requester, not executed directly."
        )


register(HITLRequestTool())

