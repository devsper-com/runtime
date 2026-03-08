import json
import re
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate

PROMPT_TEMPLATE = """You are an AI worker in a distributed system.

Task:
{task_description}
{memory_section}

Produce the best possible output."""

PROMPT_TEMPLATE_WITH_TOOLS = """You are an AI worker in a distributed system. You may use tools.

Task:
{task_description}
{memory_section}

AVAILABLE TOOLS:
{tools_section}

To call a tool, output exactly:
TOOL: <tool_name>
INPUT: <json object with arguments>

If you do not need a tool, respond with your final answer only (no TOOL: line).
"""

TOOL_NAME_PATTERN = re.compile(r"TOOL:\s*(\S+)", re.IGNORECASE)
INPUT_PREFIX = re.compile(r"INPUT:\s*", re.IGNORECASE)


def _format_tools_section() -> str:
    from hivemind.tools.registry import list_tools
    lines = []
    for t in list_tools():
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


class Agent:
    def __init__(
        self,
        model_name: str = "gpt-4o",
        event_log: EventLog | None = None,
        use_tools: bool = False,
        max_tool_iterations: int = 5,
        memory_router=None,
        store_result_to_memory: bool = False,
    ):
        self.model_name = model_name
        self.event_log = event_log or EventLog()
        self.use_tools = use_tools
        self.max_tool_iterations = max_tool_iterations
        self.memory_router = memory_router
        self.store_result_to_memory = store_result_to_memory

    def run(self, task: Task) -> str:
        self._emit(events.AGENT_STARTED, {"task_id": task.id})
        self._emit(events.TASK_STARTED, {"task_id": task.id})

        task.status = TaskStatus.RUNNING

        memory_section = ""
        if self.memory_router and task.description:
            try:
                ctx = self.memory_router.get_memory_context(task.description)
                memory_section = "\n\nRELEVANT MEMORY\n(previous research notes etc.)\n\n" + ctx if ctx else ""
            except Exception:
                pass

        if self.use_tools:
            text = self._run_with_tools(task, memory_section)
        else:
            prompt = PROMPT_TEMPLATE.format(
                task_description=task.description,
                memory_section=memory_section,
            )
            text = generate(self.model_name, prompt)

        task.status = TaskStatus.COMPLETED
        task.result = text
        if self.store_result_to_memory and text and getattr(self.memory_router, "store", None):
            self._store_result_to_memory(task, text)
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

    def _run_with_tools(self, task: Task, memory_section: str = "") -> str:
        from hivemind.tools.tool_runner import run_tool

        tools_section = _format_tools_section()
        prompt = PROMPT_TEMPLATE_WITH_TOOLS.format(
            task_description=task.description,
            memory_section=memory_section,
            tools_section=tools_section,
        )
        conversation = [prompt]
        for _ in range(self.max_tool_iterations):
            full_prompt = "\n\n".join(conversation)
            response = generate(self.model_name, full_prompt)
            tool_name, tool_args = _parse_tool_call(response)
            if tool_name is None:
                return response.strip()
            result = run_tool(tool_name, tool_args)
            self._emit(
                events.TOOL_CALLED,
                {"task_id": task.id, "tool": tool_name, "result_preview": result[:200]},
            )
            conversation.append(f"Response:\n{response}")
            conversation.append(f"Tool result ({tool_name}):\n{result}")
        return conversation[-1].strip() or "Max tool iterations reached."

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
