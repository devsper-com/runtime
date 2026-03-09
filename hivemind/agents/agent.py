import asyncio
import json
import os
import re
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate

PROMPT_TEMPLATE = """{role_prefix}

Task:
{task_description}
{memory_section}

Produce the best possible output. Output only the requested content; do not describe your role or other projects."""

PROMPT_TEMPLATE_WITH_TOOLS = """{role_prefix} You may use tools.

Task:
{task_description}
{memory_section}

Output only the requested content; do not describe your role or other projects.

AVAILABLE TOOLS:
{tools_section}

To call a tool, output exactly:
TOOL: <tool_name>
INPUT: <json object with arguments>

If you do not need a tool, respond with your final answer only (no TOOL: line).
"""

TOOL_NAME_PATTERN = re.compile(r"TOOL:\s*(\S+)", re.IGNORECASE)
INPUT_PREFIX = re.compile(r"INPUT:\s*", re.IGNORECASE)


def _format_tools_section(tools: list | None = None) -> str:
    if tools is None:
        from hivemind.tools.registry import list_tools
        tools = list_tools()
    lines = []
    for t in tools:
        lines.append(f"- {t.name}: {t.description}")
        lines.append(f"  input_schema: {json.dumps(t.input_schema)}")
    return "\n".join(lines)


def _parse_tool_call(text: str) -> tuple[str | None, dict | None]:
    """Return (tool_name, args) if a tool call is found, else (None, None)."""
    name_m = TOOL_NAME_PATTERN.search(text)
    if not name_m:
        return None, None
    name = name_m.group(1).strip()
    after_name = text[name_m.end() :]
    input_m = INPUT_PREFIX.search(after_name)
    if not input_m:
        return None, None
    start = input_m.end()
    rest = after_name[start:].lstrip()
    if not rest.startswith("{"):
        return name, {}
    depth = 0
    end = 0
    for i, c in enumerate(rest):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == 0:
        return name, {}
    try:
        args = json.loads(rest[:end])
    except json.JSONDecodeError:
        return name, {}
    return name, args if isinstance(args, dict) else {}


def _parse_all_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Return all (tool_name, args) pairs found in text (multiple TOOL:/INPUT: blocks)."""
    out: list[tuple[str, dict]] = []
    rest = text
    while True:
        name_m = TOOL_NAME_PATTERN.search(rest)
        if not name_m:
            break
        name = name_m.group(1).strip()
        after_name = rest[name_m.end() :]
        input_m = INPUT_PREFIX.search(after_name)
        if not input_m:
            break
        start = input_m.end()
        rest = after_name[start:].lstrip()
        if not rest.startswith("{"):
            out.append((name, {}))
            continue
        depth = 0
        end = 0
        for i, c in enumerate(rest):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == 0:
            out.append((name, {}))
            continue
        try:
            args = json.loads(rest[:end])
        except json.JSONDecodeError:
            args = {}
        out.append((name, args if isinstance(args, dict) else {}))
        rest = rest[end:].lstrip()
    return out


class Agent:
    def __init__(
        self,
        model_name: str = "gpt-4o",
        event_log: EventLog | None = None,
        use_tools: bool = False,
        max_tool_iterations: int = 5,
        memory_router=None,
        store_result_to_memory: bool = False,
        reasoning_store=None,
        user_task: str | None = None,
        parallel_tools: bool = True,
    ):
        self.model_name = model_name
        self.event_log = event_log or EventLog()
        self.use_tools = use_tools
        self.max_tool_iterations = max_tool_iterations
        self.memory_router = memory_router
        self.store_result_to_memory = store_result_to_memory
        self.reasoning_store = reasoning_store
        self.user_task = user_task
        self.parallel_tools = parallel_tools and os.environ.get("HIVEMIND_DISABLE_PARALLEL_TOOLS", "").strip() != "1"

    def run(self, task: Task, model_override: str | None = None) -> str:
        model = model_override if model_override else self.model_name
        self._emit(events.AGENT_STARTED, {"task_id": task.id})
        self._emit(events.TASK_STARTED, {"task_id": task.id})

        task.status = TaskStatus.RUNNING

        memory_section = ""
        if self.memory_router and task.description:
            try:
                # Bias memory retrieval by user goal so subtasks don't pull off-topic context
                query = task.description
                if self.user_task and self.user_task.strip():
                    query = f"{self.user_task.strip()} {task.description}".strip()
                ctx = self.memory_router.get_memory_context(query)
                memory_section = "\n\nRELEVANT MEMORY\n(previous research notes etc.)\n\n" + ctx if ctx else ""
            except Exception:
                pass

        from hivemind.agents.roles import get_role_config
        role_config = get_role_config(getattr(task, "role", None))
        role_prefix = role_config.prompt_prefix

        if self.use_tools:
            text = self._run_with_tools(task, memory_section, role_prefix=role_prefix, model_name=model)
        else:
            prompt = PROMPT_TEMPLATE.format(
                role_prefix=role_prefix,
                task_description=task.description,
                memory_section=memory_section,
            )
            text = generate(model, prompt)

        task.status = TaskStatus.COMPLETED
        task.result = text
        if self.store_result_to_memory and text and getattr(self.memory_router, "store", None):
            self._store_result_to_memory(task, text)
        if self.reasoning_store and text:
            try:
                node = self.reasoning_store.add_node(
                    agent_id=getattr(task, "role", "") or "agent",
                    task_id=task.id,
                    content=text[:10000],
                )
                self._emit(events.REASONING_NODE_ADDED, {"node_id": node.id, "task_id": task.id})
            except Exception:
                pass
        self._emit(events.TASK_COMPLETED, {"task_id": task.id})
        self._emit(events.AGENT_FINISHED, {"task_id": task.id})

        return text

    def _store_result_to_memory(self, task: Task, text: str) -> None:
        from hivemind.memory.memory_store import MemoryStore
        from hivemind.memory.memory_types import MemoryRecord, MemoryType
        from hivemind.memory.memory_store import generate_memory_id
        from hivemind.memory.memory_index import MemoryIndex

        store = getattr(self.memory_router, "store", None)
        if not isinstance(store, MemoryStore):
            return
        record = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.SEMANTIC,
            source_task=task.id,
            content=text[:10000],
            tags=["agent_result", task.id],
        )
        index = getattr(self.memory_router, "index", None)
        if isinstance(index, MemoryIndex):
            record = index.ensure_embedding(record)
        store.store(record)

    def _run_with_tools(
        self,
        task: Task,
        memory_section: str = "",
        role_prefix: str = "",
        model_name: str | None = None,
    ) -> str:
        from hivemind.tools.selector import get_tools_for_task
        from hivemind.tools.tool_runner import run_tool

        model = model_name or self.model_name
        role = getattr(task, "role", None)
        task_type = role or "general"
        score_store = None
        try:
            from hivemind.tools.scoring import get_default_score_store
            score_store = get_default_score_store()
        except Exception:
            pass
        tools = get_tools_for_task(
            task.description if task else "",
            role=role,
            score_store=score_store,
        )
        tools_section = _format_tools_section(tools)
        prompt = PROMPT_TEMPLATE_WITH_TOOLS.format(
            role_prefix=role_prefix,
            task_description=task.description,
            memory_section=memory_section,
            tools_section=tools_section,
        )
        conversation = [prompt]
        for _ in range(self.max_tool_iterations):
            full_prompt = "\n\n".join(conversation)
            response = generate(model, full_prompt)
            tool_calls = _parse_all_tool_calls(response)
            if not tool_calls:
                return response.strip()
            if len(tool_calls) == 1 or not self.parallel_tools:
                tool_name, tool_args = tool_calls[0]
                result = run_tool(tool_name, tool_args, task_type=task_type)
                self._emit(
                    events.TOOL_CALLED,
                    {"task_id": task.id, "tool": tool_name, "result_preview": (result or "")[:200]},
                )
                conversation.append(f"Response:\n{response}")
                conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
                continue
            results = self._run_tools_parallel_sync(tool_calls, task_type, task)
            conversation.append(f"Response:\n{response}")
            for (tool_name, _), result in zip(tool_calls, results):
                self._emit(
                    events.TOOL_CALLED,
                    {"task_id": task.id, "tool": tool_name, "result_preview": (result or "")[:200]},
                )
                conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
        return conversation[-1].strip() or "Max tool iterations reached."

    def _run_tools_parallel_sync(
        self,
        tool_calls: list[tuple[str, dict]],
        task_type: str,
        task: Task,
    ) -> list[str]:
        """Run multiple tool calls in parallel (sync entry point)."""
        from hivemind.tools.tool_runner import run_tool
        loop = asyncio.new_event_loop()
        try:
            async def run_one(name: str, args: dict) -> str:
                return await loop.run_in_executor(
                    None, lambda n=name, a=args: run_tool(n, a, task_type=task_type)
                )
            async def run_all() -> list[str]:
                tasks = [run_one(name, args) for name, args in tool_calls]
                return list(await asyncio.gather(*tasks, return_exceptions=True))
            raw = loop.run_until_complete(run_all())
            out: list[str] = []
            for r in raw:
                if isinstance(r, Exception):
                    out.append(f"Tool error: {type(r).__name__}: {r}")
                else:
                    out.append(r or "")
            return out
        finally:
            loop.close()

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
