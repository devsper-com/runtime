"""
Simple model invocation layer.

generate(model_name, prompt) -> text

Keeps agent code clean. Plug in OpenAI, Claude, Gemini later without touching agent logic.
"""


def generate(model_name: str, prompt: str) -> str:
    """Call the model with the given prompt and return text output."""
    return f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"
