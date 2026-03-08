"""
Model invocation layer: generate(model_name, prompt) -> text.

Uses ProviderRouter to select provider by model name. When model_name is "auto",
use resolve_model(spec, task_type) first to get a concrete model (e.g. from config).
Flow: task_type → model_router.select_model() → provider_router → provider.generate()
"""

from hivemind.providers.model_router import TaskType, select_model
from hivemind.providers.router import get_router


def resolve_model(model_spec: str, task_type: TaskType) -> str:
    """If model_spec is 'auto', return model_router.select_model(task_type); else return model_spec."""
    if (model_spec or "").strip().lower() == "auto":
        return select_model(task_type)
    return model_spec or "mock"


def generate(model_name: str, prompt: str, stream: bool = False):
    """Call the model with the given prompt and return text output (or stream iterator if stream=True)."""
    provider = get_router().get_provider(model_name)
    return provider.generate(model_name, prompt, stream=stream)
