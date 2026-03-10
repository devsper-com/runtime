import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.utils.event_logger import EventLog
from hivemind.utils.models import generate


@dataclass
class AgentRequest:
    """Serializable input for Agent.run. All context comes in via this object."""
    task: Task
    memory_context: str
    tools: list[str]  # tool names only
    model: str
    system_prompt: str
    prefetch_used: bool

    def to_dict(self) -> dict:
        return {
            "task": self.task.to_dict(),
            "memory_context": self.memory_context,
            "tools": list(self.tools),
            "model": self.model,
            "system_prompt": self.system_prompt,
            "prefetch_used": self.prefetch_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRequest":
        return cls(
            task=Task.from_dict(data["task"]),
            memory_context=data.get("memory_context", ""),
            tools=list(data.get("tools", [])),
            model=data.get("model", "mock"),
            system_prompt=data.get("system_prompt", ""),
            prefetch_used=data.get("prefetch_used", False),
        )


@dataclass
class AgentResponse:
    """Serializable output from Agent.run."""
    task_id: str
    result: str
    tools_called: list[str]
    broadcasts: list[str]
    tokens_used: int | None
    duration_seconds: float
    error: str | None
    success: bool

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "result": self.result if self.result is not None else "",
            "tools_called": list(self.tools_called),
            "broadcasts": list(self.broadcasts),
            "tokens_used": self.tokens_used,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentResponse":
        return cls(
            task_id=data["task_id"],
            result=data.get("result", ""),
            tools_called=list(data.get("tools_called", [])),
            broadcasts=list(data.get("broadcasts", [])),
            tokens_used=data.get("tokens_used"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            error=data.get("error"),
            success=bool(data.get("success", False)),
        )

BROADCAST_PREFIX = re.compile(r"^\s*BROADCAST:\s*(.+?)(?=\n\n|\n[A-Z]|\Z)", re.DOTALL | re.IGNORECASE)

PROMPT_TEMPLATE = """{role_prefix}

Task:
{task_description}
{memory_section}
{message_bus_section}

Produce the best possible output. Output only the requested content; do not describe your role or other projects."""

PROMPT_TEMPLATE_WITH_TOOLS = """{role_prefix} You may use tools.

Task:
{task_description}
{memory_section}
{message_bus_section}

Output only the requested content; do not describe your role or other projects.

AVAILABLE TOOLS:
{tools_section}

To call a tool, output exactly:
TOOL: <tool_name>
INPUT: <json object with arguments>

When the task requires listing files, reading/writing files, or running commands, you MUST use the appropriate tool above (output TOOL: and INPUT:). Do not describe what you would do or say you cannot do it—call the tool and use its result. Use the exact tool name as shown in the list (e.g. filesystem.list_dir for listing a directory).

You are in an automated workflow. Do not ask the user for their OS, environment, or to specify paths—use the task description and call tools with the paths/data given there.

If you do not need a tool, respond with your final answer only (no TOOL: line).
"""

BROADCAST_INSTRUCTION = """
If you discover a fact, constraint, or finding that would help other agents working on related tasks, begin your response with:
BROADCAST: <one sentence finding>
Your actual response follows on the next line.
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


def _get_tools_by_names(names: list[str]) -> list:
    """Resolve tool names to tool objects from registry."""
    from hivemind.tools.registry import get
    out = []
    for n in names:
        t = get(n)
        if t is not None:
            out.append(t)
    return out


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
        message_bus=None,
        audit_logger=None,
        audit_run_id: str = "",
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
        self.message_bus = message_bus
        self.audit_logger = audit_logger
        self.audit_run_id = audit_run_id or ""

    def run(self, request: AgentRequest) -> AgentResponse:
        """Stateless run: all context in AgentRequest, all output in AgentResponse."""
        import time
        t0 = time.perf_counter()
        task_id = request.task.id
        try:
            self._emit(events.AGENT_STARTED, {"task_id": task_id})
            self._emit(events.TASK_STARTED, {"task_id": task_id})

            memory_section = ""
            if request.memory_context:
                memory_section = "\n\nRELEVANT MEMORY\n(previous research notes etc.)\n\n" + request.memory_context

            if self.use_tools and request.tools:
                tools_objs = _get_tools_by_names(request.tools)
                text, tools_called = self._run_with_tools_for_request(
                    request, memory_section, tools_objs
                )
            else:
                prompt = PROMPT_TEMPLATE.format(
                    role_prefix=request.system_prompt,
                    task_description=request.task.description,
                    memory_section=memory_section,
                    message_bus_section="",
                )
                text = generate(request.model, prompt)
                tools_called = []

            text, broadcasts = self._strip_broadcast_and_collect(task_id, text)

            if self.store_result_to_memory and text and getattr(self.memory_router, "store", None):
                self._store_result_to_memory(request.task, text)
            if self.reasoning_store and text:
                try:
                    node = self.reasoning_store.add_node(
                        agent_id=getattr(request.task, "role", "") or "agent",
                        task_id=task_id,
                        content=text[:10000],
                    )
                    self._emit(events.REASONING_NODE_ADDED, {"node_id": node.id, "task_id": task_id})
                except Exception:
                    pass
            self._emit(events.TASK_COMPLETED, {"task_id": task_id})
            self._emit(events.AGENT_FINISHED, {"task_id": task_id})

            duration = time.perf_counter() - t0
            return AgentResponse(
                task_id=task_id,
                result=text,
                tools_called=tools_called,
                broadcasts=broadcasts,
                tokens_used=None,
                duration_seconds=duration,
                error=None,
                success=True,
            )
        except Exception as e:
            duration = time.perf_counter() - t0
            self._emit(events.TASK_FAILED, {"task_id": task_id, "error": str(e)})
            return AgentResponse(
                task_id=task_id,
                result="",
                tools_called=[],
                broadcasts=[],
                tokens_used=None,
                duration_seconds=duration,
                error=str(e),
                success=False,
            )

    def build_request(
        self,
        task: Task,
        model_override: str | None = None,
        prefetch_result=None,
    ) -> AgentRequest:
        """Build AgentRequest for this task (for use with sandbox or external runner)."""
        memory_section = ""
        if prefetch_result and getattr(prefetch_result, "memory_context", None):
            ctx = prefetch_result.memory_context
            memory_section = ctx or ""
        elif self.memory_router and task.description:
            try:
                query = task.description
                if self.user_task and self.user_task.strip():
                    query = f"{self.user_task.strip()} {task.description}".strip()
                memory_section = self.memory_router.get_memory_context(query) or ""
            except Exception:
                pass
        message_bus_section = ""
        if self.message_bus:
            message_bus_section = self.message_bus.get_context_sync(task.id) or ""
        if message_bus_section:
            memory_section = (memory_section + "\n\n" + message_bus_section).strip()
        from hivemind.agents.roles import get_role_config
        role_config = get_role_config(getattr(task, "role", None))
        broadcast_instruction = BROADCAST_INSTRUCTION if (self.message_bus and message_bus_section) else ""
        system_prompt = role_config.prompt_prefix + broadcast_instruction if broadcast_instruction else role_config.prompt_prefix
        tools_names: list[str] = []
        if self.use_tools:
            if prefetch_result and getattr(prefetch_result, "tools", None):
                tools_names = [t.name for t in prefetch_result.tools]
            else:
                try:
                    from hivemind.tools.selector import get_tools_for_task
                    from hivemind.tools.scoring import get_default_score_store
                    score_store = get_default_score_store()
                except Exception:
                    score_store = None
                tools = get_tools_for_task(
                    task.description or "",
                    role=getattr(task, "role", None),
                    score_store=score_store,
                )
                tools_names = [t.name for t in tools]
        model = model_override if model_override else self.model_name
        return AgentRequest(
            task=task,
            memory_context=memory_section,
            tools=tools_names,
            model=model,
            system_prompt=system_prompt,
            prefetch_used=prefetch_result is not None,
        )

    def apply_response(self, task: Task, response: AgentResponse) -> None:
        """Apply AgentResponse to task (status, result, error)."""
        task.status = TaskStatus.COMPLETED if response.success else TaskStatus.FAILED
        task.result = response.result
        if response.error:
            task.error = response.error

    def run_task(
        self,
        task: Task,
        model_override: str | None = None,
        prefetch_result=None,
    ) -> str:
        """Backward-compat: build AgentRequest from task and prefetch, run, mutate task, return result."""
        request = self.build_request(task, model_override=model_override, prefetch_result=prefetch_result)
        response = self.run(request)
        self.apply_response(task, response)
        return response.result

    def _strip_broadcast_and_collect(self, task_id: str, text: str) -> tuple[str, list[str]]:
        """If text starts with BROADCAST:, optionally emit to message_bus, strip; return (rest, list of findings)."""
        collected: list[str] = []
        rest = text
        while rest:
            m = BROADCAST_PREFIX.match(rest)
            if not m:
                break
            finding = m.group(1).strip()
            collected.append(finding)
            if self.message_bus:
                self.message_bus.broadcast_sync(task_id, finding, tags=[])
            rest = rest[m.end():].lstrip()
        return (rest, collected)

    def _strip_broadcast_and_emit(self, task: Task, text: str) -> str:
        """If text starts with BROADCAST:, emit to message_bus and strip; return rest."""
        rest, _ = self._strip_broadcast_and_collect(task.id, text or "")
        return rest

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

    def _run_with_tools_for_request(
        self,
        request: AgentRequest,
        memory_section: str,
        tools_list: list,
    ) -> tuple[str, list[str]]:
        """Run tool loop for a request; return (result_text, list of tool names called)."""
        from hivemind.tools.tool_runner import run_tool

        task = request.task
        task_type = getattr(task, "role", None) or "general"
        tools_section = _format_tools_section(tools_list)
        prompt = PROMPT_TEMPLATE_WITH_TOOLS.format(
            role_prefix=request.system_prompt,
            task_description=task.description,
            memory_section=memory_section,
            message_bus_section="",
            tools_section=tools_section,
        )
        conversation = [prompt]
        tools_called: list[str] = []
        for _ in range(self.max_tool_iterations):
            full_prompt = "\n\n".join(conversation)
            response = generate(request.model, full_prompt)
            tool_calls = _parse_all_tool_calls(response)
            if not tool_calls:
                return (response.strip(), tools_called)
            for (tool_name, _) in tool_calls:
                tools_called.append(tool_name)
            if len(tool_calls) == 1 or not self.parallel_tools:
                tool_name, tool_args = tool_calls[0]
                result = run_tool(tool_name, tool_args, task_type=task_type)
                self._emit_tool_called_audit(task.id, tool_name, result)
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
                self._emit_tool_called_audit(task.id, tool_name, result)
                self._emit(
                    events.TOOL_CALLED,
                    {"task_id": task.id, "tool": tool_name, "result_preview": (result or "")[:200]},
                )
                conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
        return (conversation[-1].strip() or "Max tool iterations reached.", tools_called)

    def _run_with_tools(
        self,
        task: Task,
        memory_section: str = "",
        role_prefix: str = "",
        model_name: str | None = None,
        tools_list: list | None = None,
        message_bus_section: str = "",
    ) -> str:
        from hivemind.tools.selector import get_tools_for_task
        from hivemind.tools.tool_runner import run_tool

        model = model_name or self.model_name
        role = getattr(task, "role", None)
        task_type = role or "general"
        if tools_list is not None:
            tools = tools_list
        else:
            score_store = None
            try:
                from hivemind.tools.scoring import get_default_score_store
                score_store = get_default_score_store()
            except Exception:
                score_store = None
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
            message_bus_section=message_bus_section,
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
                self._emit_tool_called_audit(task.id, tool_name, result)
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
                self._emit_tool_called_audit(task.id, tool_name, result)
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

    def _emit_tool_called_audit(self, task_id: str, tool_name: str, result: str) -> None:
        if not self.audit_logger or not self.audit_run_id:
            return
        try:
            from hivemind.audit.logger import make_audit_record
            rec = make_audit_record(
                run_id=self.audit_run_id,
                task_id=task_id,
                event_type="TOOL_CALLED",
                actor=task_id,
                resource=tool_name,
                input_text=tool_name,
                output_text=(result or "")[:2000],
            )
            self.audit_logger.log(rec)
        except Exception:
            pass

    def _emit(self, event_type: events, payload: dict) -> None:
        self.event_log.append_event(
            Event(timestamp=datetime.now(timezone.utc), type=event_type, payload=payload)
        )
