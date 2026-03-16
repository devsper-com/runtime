"""
Provider base interface.

All providers implement generate(model, prompt, stream=False).
When stream=True, yield chunks; when stream=False, return full text.
"""

from abc import ABC, abstractmethod
from typing import Iterator


class BaseProvider(ABC):
    """Common interface for OpenAI, Anthropic, Gemini, GitHub, and mock."""

    @abstractmethod
    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        """Return model output (str or iterator of chunks when stream=True)."""
        ...


def _ensure_str(result) -> str:
    """If result is an iterator (stream=True), consume and return concatenated string."""
    if hasattr(result, "__iter__") and not isinstance(result, str):
        return "".join(result)
    return result if isinstance(result, str) else str(result)


def _mock_planner_response(prompt: str) -> str:
    """Return a valid numbered list so the planner can parse subtasks when no API key is set."""
    if "Break the following task into" in prompt or "smaller steps" in prompt:
        task_part = "Summarize the topic"  # fallback
        if "Task:" in prompt:
            start = prompt.find("Task:") + 5
            end = prompt.find("\n", start) if "\n" in prompt[start:] else len(prompt)
            task_part = prompt[start:end].strip()[:80]
        return (
            f"1. Define and scope the topic: {task_part}\n"
            "2. Gather key points and examples\n"
            "3. Synthesize into a clear summary\n"
            "4. Add one or two concrete details\n"
            "5. Polish into a single paragraph"
        )
    return f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"


def _mock_agent_response(prompt: str) -> str:
    """Return a short on-topic stub for agent tasks so demo output is coherent."""
    if "Task:" in prompt:
        task_start = prompt.find("Task:") + 5
        rest = prompt[task_start:].strip()
        first_line = rest.split("\n")[0].strip()[:100]
        return (
            f"[Mock] Summary for: {first_line}\n\n"
            "Swarm intelligence is collective behavior that emerges from many simple agents "
            "following local rules (e.g. ants, bees, flocks). No central controller is needed; "
            "coordination arises from stigmergy, feedback, and self-organization."
        )
    return f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"


class MockProvider(BaseProvider):
    """In-memory provider for tests and default stub. No API key required."""

    def generate(self, model: str, prompt: str, stream: bool = False) -> str | Iterator[str]:
        if "Break the following task" in prompt or "5 smaller steps" in prompt:
            text = _mock_planner_response(prompt)
        elif "You are an AI worker" in prompt or "Task:" in prompt:
            text = _mock_agent_response(prompt)
        else:
            text = f"Completed: {prompt[:200]}{'...' if len(prompt) > 200 else ''}"
        if stream:
            def _gen() -> Iterator[str]:
                yield text
            return _gen()
        return text
