from __future__ import annotations

import asyncio

from devsper.agents.agent import Agent
from devsper.types.task import Task
from devsper.utils.models import generate
from devsper.tools.tool_runner import run_tool


def _extract_tool_calls(text: str) -> list[tuple[str, dict]]:
    try:
        from devsper.agents.agent import _parse_all_tool_calls  # type: ignore

        return _parse_all_tool_calls(text)
    except Exception:
        return []


class AgentRunner:
    """Async wrapper for agent execution with optional streaming tool handling."""

    def __init__(self, agent: Agent, streaming_tools: bool = False) -> None:
        self._agent = agent
        self._streaming_tools = bool(streaming_tools)

    async def run_task(self, task: Task, model_override: str | None = None) -> str:
        if self._streaming_tools:
            try:
                return await asyncio.to_thread(
                    self._run_task_streaming_tools_sync,
                    task,
                    model_override,
                )
            except Exception:
                pass
        return await asyncio.to_thread(
            self._agent.run_task,
            task,
            model_override,
            None,
        )

    def _run_task_streaming_tools_sync(
        self,
        task: Task,
        model_override: str | None = None,
    ) -> str:
        request = self._agent.build_request(task, model_override=model_override)
        if not getattr(self._agent, "use_tools", False) or not request.tools:
            return self._agent.run_task(task, model_override=model_override, prefetch_result=None)

        from devsper.agents.agent import PROMPT_TEMPLATE_WITH_TOOLS, _format_tools_section, _get_tools_by_names

        tools = _get_tools_by_names(request.tools)
        prompt = PROMPT_TEMPLATE_WITH_TOOLS.format(
            role_prefix=request.system_prompt,
            task_description=request.task.description,
            memory_section=request.memory_context or "",
            message_bus_section="",
            tools_section=_format_tools_section(tools),
        )
        conversation = [prompt]
        task_type = getattr(task, "role", None) or "general"

        for _ in range(max(1, int(getattr(self._agent, "max_tool_iterations", 5)))):
            streamed = generate(request.model, "\n\n".join(conversation), stream=True)
            text = "".join(streamed) if hasattr(streamed, "__iter__") else str(streamed)
            calls = _extract_tool_calls(text)
            if not calls:
                return (text or "").strip()

            conversation.append(f"Response:\n{text}")
            for name, args in calls:
                result = run_tool(name, args, task_type=task_type)
                conversation.append(f"Tool result ({name}):\n{result or ''}")

        return "Max tool iterations reached."

