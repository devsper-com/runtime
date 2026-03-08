"""
Model invocation layer: generate(model_name, prompt) -> text.

Uses ProviderRouter to select provider by model name. Agent and planner
call this; they do not know which provider is used.
"""

from hivemind.providers.router import get_router


def generate(model_name: str, prompt: str) -> str:
    """Call the model with the given prompt and return text output."""
    provider = get_router().get_provider(model_name)
    return provider.generate(model_name, prompt)
