import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from devsper.types.task import Task, TaskStatus
from devsper.types.event import Event, events
from devsper.utils.event_logger import EventLog
from devsper.utils.models import generate
from devsper.events import (
    ClarificationField,
    ClarificationRequest,
)

log = logging.getLogger(__name__)


@dataclass
class AgentRequest:
    """Serializable input for Agent.run. All context comes in via this object."""

    task: Task
    memory_context: str
    tools: list[str]  # tool names only
    model: str
    system_prompt: str
    prefetch_used: bool
    # Distributed tool protocol: controller runs tools, worker sends tool_calls and receives tool_results.
    tool_results: list[dict] | None = None  # [{"name": str, "result": str}, ...]
    distributed_tools: bool = (
        False  # if True, return tool_calls in response instead of running locally
    )

    def to_dict(self) -> dict:
        out = {
            "task": self.task.to_dict(),
            "memory_context": self.memory_context,
            "tools": list(self.tools),
            "model": self.model,
            "system_prompt": self.system_prompt,
            "prefetch_used": self.prefetch_used,
        }
        if self.tool_results is not None:
            out["tool_results"] = list(self.tool_results)
        if self.distributed_tools:
            out["distributed_tools"] = True
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "AgentRequest":
        tr = data.get("tool_results")
        if tr is not None and not isinstance(tr, list):
            tr = None
        return cls(
            task=Task.from_dict(data["task"]),
            memory_context=data.get("memory_context", ""),
            tools=list(data.get("tools", [])),
            model=data.get("model", "mock"),
            system_prompt=data.get("system_prompt", ""),
            prefetch_used=data.get("prefetch_used", False),
            tool_results=tr,
            distributed_tools=bool(data.get("distributed_tools", False)),
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
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    # Distributed tool protocol: when model requested tool calls, worker sends these to controller.
    tool_calls: list[dict] | None = None  # [{"name": str, "arguments": dict}, ...]

    def to_dict(self) -> dict:
        out = {
            "task_id": self.task_id,
            "result": self.result if self.result is not None else "",
            "tools_called": list(self.tools_called),
            "broadcasts": list(self.broadcasts),
            "tokens_used": self.tokens_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": self.cost_usd,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "success": self.success,
        }
        if self.tool_calls:
            out["tool_calls"] = list(self.tool_calls)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "AgentResponse":
        tc = data.get("tool_calls")
        if tc is not None and not isinstance(tc, list):
            tc = None
        return cls(
            task_id=data["task_id"],
            result=data.get("result", ""),
            tools_called=list(data.get("tools_called", [])),
            broadcasts=list(data.get("broadcasts", [])),
            tokens_used=data.get("tokens_used"),
            prompt_tokens=data.get("prompt_tokens"),
            completion_tokens=data.get("completion_tokens"),
            cost_usd=data.get("cost_usd"),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            error=data.get("error"),
            success=bool(data.get("success", False)),
            tool_calls=tc,
        )


BROADCAST_PREFIX = re.compile(
    r"^\s*BROADCAST:\s*(.+?)(?=\n\n|\n[A-Z]|\Z)", re.DOTALL | re.IGNORECASE
)

PROMPT_TEMPLATE = """{role_prefix}

Task:
{task_description}
{memory_section}
{message_bus_section}

Produce the best possible output. Output only the requested content; do not describe your role or other projects.

If user input is required, state exactly what information is missing.
"""

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

If you need user input before continuing, call this tool exactly:
TOOL: hitl.request
INPUT: {{"context":"one sentence reason","priority":1,"timeout_seconds":120,"fields":[{{"type":"mcq","question":"Select one option","options":["Option A","Option B"],"default":null,"required":true}}]}}

Do not ask free-form clarification questions in plain text. Use `hitl.request`.
"""

BROADCAST_INSTRUCTION = """
If you discover a fact, constraint, or finding that would help other agents working on related tasks, begin your response with:
BROADCAST: <one sentence finding>
Your actual response follows on the next line.
"""


class ClarificationDetector:
    """
    Detects when an agent response is asking for clarification
    rather than making progress on the task.
    """

    ASK_PATTERNS = [
        r"please (provide|share|give|specify|clarify|confirm)",
        r"(could|can|would) you (please )?(provide|share|tell|give|confirm|specify)",
        r"to (proceed|continue|help you), (i need|please provide)",
        r"answer these (quick )?questions",
        r"please choose",
        r"choose one of",
        r"which path",
        r"^\d+\)\s+.+",  # numbered list of questions
        r"before i (can |)(proceed|start|begin|continue)",
    ]

    MCQ_PATTERNS = [
        r"- [A-D]:",  # - A: option, - B: option
        r"\(choose one\)",
        r"select one of",
        r"options?:.*\n.*-",
        # A) / B) / Option A — / Option B: style letter choices
        r"(?m)^\s*(?:[0-9a-fA-F-]{4,}\s*:\s*)?(?:Option\s+)?[A-D]\s*(?:\)|:|\.|\u2014|\u2013|\u2212|-)\s+.+",
    ]

    def _parse_hitl_request_directive(self, text: str) -> ClarificationRequest | None:
        """
        Parse a deterministic HITL directive line:

            HITL_REQUEST: { ...json... }

        Returns a ClarificationRequest if parsing/validation succeeds, else None
        (callers fall back to regex detection).
        """

        token = "HITL_REQUEST:"
        pos = (text or "").find(token)
        if pos < 0:
            return None

        # Extract JSON starting at the first '{' after the token. We use raw_decode
        # to allow trailing characters after the JSON block.
        after = text[pos + len(token) :]
        brace_pos = after.find("{")
        if brace_pos < 0:
            return None

        decoder = json.JSONDecoder()
        try:
            data, _end = decoder.raw_decode(after[brace_pos:])
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        fields_raw = data.get("fields") or []
        if not isinstance(fields_raw, list) or not fields_raw:
            return None

        fields: list[ClarificationField] = []
        for f in fields_raw:
            if not isinstance(f, dict):
                return None
            f_type = f.get("type")
            q = f.get("question")
            if not isinstance(f_type, str) or not isinstance(q, str):
                return None
            options = f.get("options")
            if options is None:
                options_val = None
            elif isinstance(options, list):
                options_val = [str(x) for x in options]
            else:
                options_val = None

            default_val = f.get("default")
            default_str = None if default_val is None else str(default_val)
            required_val = f.get("required", True)
            required_bool = bool(required_val)

            fields.append(
                ClarificationField(
                    type=f_type,  # type: ignore[arg-type]
                    question=q,
                    options=options_val,
                    default=default_str,
                    required=required_bool,
                )
            )

        context = data.get("context")
        context_str = context if isinstance(context, str) else self._extract_context(text)
        if not context_str:
            context_str = ""

        priority_raw = data.get("priority", 1)
        timeout_raw = data.get("timeout_seconds", data.get("timeout", 120))
        try:
            priority = int(priority_raw)
        except Exception:
            priority = 1
        try:
            timeout_seconds = int(timeout_raw)
        except Exception:
            timeout_seconds = 120

        return ClarificationRequest(
            request_id=str(uuid.uuid4()),
            task_id="",  # filled by caller
            agent_role="",  # filled by caller
            fields=fields,
            context=context_str,
            priority=priority,
            timeout_seconds=timeout_seconds,
        )

    def detect(self, text: str) -> ClarificationRequest | None:
        """
        Returns ClarificationRequest if text is asking for clarification,
        None if it's a normal agent response making progress.
        """
        if not (text or "").strip():
            return None

        # Primary path: deterministic HITL directive emitted by the model.
        directive = self._parse_hitl_request_directive(text)
        if directive is not None:
            return directive

        ask_score = sum(
            1
            for p in self.ASK_PATTERNS
            if re.search(p, text, re.IGNORECASE | re.MULTILINE)
        )
        if ask_score < 2:
            # Allow explicit structured MCQ blocks even if only one ASK pattern matched.
            if any(
                re.search(p, text, re.IGNORECASE | re.MULTILINE)
                for p in self.MCQ_PATTERNS
            ):
                pass
            # Single yes/no question: allow with 1 pattern if we parse a confirm
            elif not re.search(r"\(yes/no\)|\(y/n\)", text, re.IGNORECASE):
                return None
        fields = self._parse_fields(text)
        if not fields:
            return None
        return ClarificationRequest(
            request_id=str(uuid.uuid4()),
            task_id="",  # filled by caller
            agent_role="",  # filled by caller
            fields=fields,
            context=self._extract_context(text),
        )

    def _parse_fields(self, text: str) -> list[ClarificationField]:
        fields: list[ClarificationField] = []
        # Single yes/no question (no numbered list)
        yes_no = re.search(
            r"(.+?)\s*\(yes/no\)|\(y/n\)",
            text.strip(),
            re.IGNORECASE | re.DOTALL,
        )
        if yes_no:
            q = yes_no.group(1).strip()
            if len(q) > 5:
                fields.append(
                    ClarificationField(
                        type="confirm",
                        question=q[:500],
                        options=None,
                        default=None,
                        required=True,
                    )
                )
                return fields

        # Lettered choices like:
        # A) Upload / point to a dataset you already have
        # ...
        # B) I collect public-source data for you
        letter_opt_re = re.compile(
            r"(?m)^\s*(?:[0-9a-fA-F-]{4,}\s*:\s*)?(?:Option\s+)?([A-D])\s*(?:\)|:|\.|\u2014|\u2013|\u2212|-)\s*(.*)$",
            flags=re.IGNORECASE,
        )
        matches = list(letter_opt_re.finditer(text))
        if len(matches) >= 2:
            # Build each option from the start line through just before the next option start.
            opts: list[str] = []
            letters: list[str] = []
            for i, m in enumerate(matches):
                letters.append((m.group(1) or "").upper())
                start_to_next = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                raw = text[m.end() : start_to_next].strip()
                first_line_tail = (m.group(2) or "").strip()
                full = (first_line_tail + " " + raw).strip()
                full = re.sub(r"\s+", " ", full)
                if full:
                    opts.append(full)

            if len(opts) >= 2:
                # Try to extract a reasonable question; fall back to a generic one.
                question = "Select one option"
                m_q = re.search(
                    r"(?is)(choose one of the two paths[^:\n]*|which path[^:\n]*|choose one[^:\n]*)",
                    text,
                )
                if m_q:
                    question = m_q.group(0).strip()
                else:
                    # Common phrasing from existing prompts
                    m_q2 = re.search(r"(?is)tell me which path[^.\n]*", text)
                    if m_q2:
                        question = m_q2.group(0).strip()
                if len(question) > 5:
                    fields.append(
                        ClarificationField(
                            type="mcq",
                            question=question[:500],
                            options=opts[:4],  # UI supports A-D; keep consistent
                            default=None,
                            required=True,
                        )
                    )
                    return fields

        # Split on numbered items: "1)", "2)", etc.
        items = re.split(r"\n\d+\)", text)
        for item in items[1:]:
            item = item.strip()
            if not item:
                continue
            options = re.findall(r"-\s+[A-D]:\s+(.+)", item)
            if options:
                question = item.split("\n")[0].strip()
                fields.append(
                    ClarificationField(
                        type="mcq",
                        question=question,
                        options=options,
                        default=None,
                        required=True,
                    )
                )
            else:
                question = item.split("\n")[0].strip()
                if question:
                    fields.append(
                        ClarificationField(
                            type="text",
                            question=question,
                            options=None,
                            default=None,
                            required=False,
                        )
                    )
        return fields

    def _extract_context(self, text: str) -> str:
        lines = text.strip().split("\n")
        for line in lines:
            if len(line) > 20 and not re.match(r"\d+\)", line):
                return line.strip()[:200]
        return ""


TOOL_NAME_PATTERN = re.compile(r"TOOL:\s*(\S+)", re.IGNORECASE)
INPUT_PREFIX = re.compile(r"INPUT:\s*", re.IGNORECASE)


def _format_tools_section(tools: list | None = None) -> str:
    if tools is None:
        from devsper.tools.registry import list_tools

        tools = list_tools()
    max_props = 8
    lines = []
    for t in tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "schema", {}) or {}
        schema_type = schema.get("type", "object")
        required = schema.get("required", []) or []
        props = schema.get("properties", {}) if isinstance(schema.get("properties", {}), dict) else {}
        compact_props: dict[str, dict] = {}
        for key in list(props.keys())[:max_props]:
            p = props.get(key, {}) or {}
            compact_props[key] = {"type": p.get("type", "string")}
        compact_schema = {
            "type": schema_type,
            "required": required[:max_props],
            "properties": compact_props,
        }
        lines.append(f"- {t.name}: {t.description}")
        lines.append(f"  input_schema: {json.dumps(compact_schema, separators=(',', ':'))}")
    return "\n".join(lines)


def _get_tools_by_names(names: list[str]) -> list:
    """Resolve tool names to tool objects from registry."""
    from devsper.tools.registry import get

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
        memory_namespace: str | None = None,
    ):
        self.model_name = model_name
        self.event_log = event_log or EventLog()
        self.use_tools = use_tools
        self.max_tool_iterations = max_tool_iterations
        self.memory_router = memory_router
        self.memory_namespace = memory_namespace
        self.store_result_to_memory = store_result_to_memory
        self.reasoning_store = reasoning_store
        self.user_task = user_task
        self.parallel_tools = (
            parallel_tools
            and os.environ.get("DEVSPER_DISABLE_PARALLEL_TOOLS", "").strip() != "1"
        )
        self.message_bus = message_bus
        self.audit_logger = audit_logger
        self.audit_run_id = audit_run_id or ""
        self.clarification_requester = None  # set by executor for human-in-the-loop

    def run(self, request: AgentRequest) -> AgentResponse:
        """Stateless run: all context in AgentRequest, all output in AgentResponse."""
        import time
        from devsper.memory.context import attach_memory_context, detach_memory_context

        t0 = time.perf_counter()
        task_id = request.task.id
        ctx = attach_memory_context(
            getattr(self.memory_router, "store", None) if self.memory_router else None,
            self.memory_namespace,
            getattr(self.event_log, "run_id", None),
        )
        try:
            self._emit(events.AGENT_STARTED, {"task_id": task_id})
            self._emit(events.TASK_STARTED, {"task_id": task_id})

            memory_section = ""
            if request.memory_context:
                memory_section = (
                    "\n\nRELEVANT MEMORY\n(previous research notes etc.)\n\n"
                    + request.memory_context
                )

            if self.use_tools and request.tools:
                tools_objs = _get_tools_by_names(request.tools)
                text, tools_called, tool_calls_out = self._run_with_tools_for_request(
                    request, memory_section, tools_objs
                )
                if tool_calls_out:
                    duration = time.perf_counter() - t0
                    self._emit(events.AGENT_FINISHED, {"task_id": task_id})
                    return AgentResponse(
                        task_id=task_id,
                        result="",
                        tools_called=tools_called,
                        broadcasts=[],
                        tokens_used=None,
                        duration_seconds=duration,
                        error=None,
                        success=True,
                        tool_calls=tool_calls_out,
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

            # Clarification: detect ask-for-input and optionally block for user response
            requester = getattr(self, "clarification_requester", None)
            clarification = None
            # Strict protocol for tool-enabled runs: HITL must be expressed via
            # deterministic `hitl.request` tool call.
            if not (self.use_tools and "hitl.request" in (request.tools or [])):
                detector = ClarificationDetector()
                clarification = detector.detect(text)

            if clarification is not None:
                clarification.task_id = request.task.id
                clarification.agent_role = (
                    getattr(request.task, "role", None) or "agent"
                )
                if requester is not None:
                    response = requester.request_clarification(clarification)
                    if response.skipped:
                        return self._run_without_clarification(request)
                    enriched_task = self._enrich_task(request.task, response.answers)
                    new_request = self.build_request(enriched_task)
                    return self.run(new_request)
                else:
                    duration = time.perf_counter() - t0
                    self._emit(
                        events.TASK_FAILED,
                        {
                            "task_id": task_id,
                            "error": f"Human-in-the-Loop required: {clarification.question}",
                        },
                    )
                    return AgentResponse(
                        task_id=task_id,
                        result=text,
                        tools_called=tools_called,
                        broadcasts=broadcasts,
                        tokens_used=None,
                        duration_seconds=duration,
                        error=f"Human-in-the-Loop required: {clarification.question}",
                        success=False,
                    )

            if (
                self.store_result_to_memory
                and text
                and getattr(self.memory_router, "store", None)
            ):
                self._store_result_to_memory(request.task, text)
            if self.reasoning_store and text:
                try:
                    node = self.reasoning_store.add_node(
                        agent_id=getattr(request.task, "role", "") or "agent",
                        task_id=task_id,
                        content=text[:10000],
                    )
                    self._emit(
                        events.REASONING_NODE_ADDED,
                        {"node_id": node.id, "task_id": task_id},
                    )
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
            log.warning(
                "Agent run failed for task %s: %s: %s",
                task_id[:12] if task_id else "?",
                type(e).__name__,
                e,
                exc_info=False,
            )
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
        finally:
            detach_memory_context(ctx)

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
        from devsper.agents.roles import get_role_config

        role_config = get_role_config(getattr(task, "role", None))
        broadcast_instruction = (
            BROADCAST_INSTRUCTION if (self.message_bus and message_bus_section) else ""
        )
        system_prompt = (
            role_config.prompt_prefix + broadcast_instruction
            if broadcast_instruction
            else role_config.prompt_prefix
        )
        tools_names: list[str] = []
        if self.use_tools:
            if prefetch_result and getattr(prefetch_result, "tools", None):
                tools_names = [t.name for t in prefetch_result.tools]
            else:
                try:
                    from devsper.tools.selector import get_tools_for_task
                    from devsper.tools.scoring import get_default_score_store

                    score_store = get_default_score_store()
                except Exception:
                    score_store = None
                tools = get_tools_for_task(
                    task.description or "",
                    role=getattr(task, "role", None),
                    score_store=score_store,
                )
                tools_names = [t.name for t in tools]
            if getattr(self, "clarification_requester", None) is not None:
                # Ensure synthetic tool is registered in process before use.
                try:
                    import devsper.tools.hitl_request  # noqa: F401
                except Exception:
                    pass
                if "hitl.request" not in tools_names:
                    tools_names.append("hitl.request")
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
        task.tokens_used = response.tokens_used
        task.prompt_tokens = response.prompt_tokens
        task.completion_tokens = response.completion_tokens
        task.cost_usd = response.cost_usd
        if response.error:
            task.error = response.error

    def run_task(
        self,
        task: Task,
        model_override: str | None = None,
        prefetch_result=None,
    ) -> str:
        """Backward-compat: build AgentRequest from task and prefetch, run, mutate task, return result."""
        request = self.build_request(
            task, model_override=model_override, prefetch_result=prefetch_result
        )
        try:
            # Preferred: Agent.run(AgentRequest)
            response = self.run(request)
        except (TypeError, AttributeError):
            # Some tests/legacy call sites monkeypatch Agent.run to accept Task.
            response = self.run(task)  # type: ignore[misc]
        # Legacy behavior: some call sites monkeypatch Agent.run to return raw text.
        if isinstance(response, str):
            response = AgentResponse(
                task_id=task.id,
                result=response,
                tools_called=[],
                broadcasts=[],
                tokens_used=None,
                duration_seconds=0.0,
                error=None,
                success=True,
            )
        self.apply_response(task, response)
        return response.result

    def _enrich_task(self, task: Task, answers: dict) -> Task:
        """Append user clarification answers to task description."""
        context_lines = ["\n\n[User provided clarification:]"]
        for question, answer in answers.items():
            context_lines.append(f"- {question}: {answer}")
        return task.model_copy(
            update={"description": task.description + "\n".join(context_lines)}
        )

    def clarify(
        self,
        context: str,
        fields: list[ClarificationField],
        timeout: int = 120,
        priority: int = 1,
    ) -> dict:
        """
        Request clarification from the user. Blocks until user responds or timeout.
        Returns answers dict (question -> answer), or {} if skipped/no requester.
        """
        requester = getattr(self, "clarification_requester", None)
        if requester is None:
            return {}
        request_id = str(uuid.uuid4())
        task_id = getattr(self, "current_task_id", "") or ""
        agent_role = getattr(self, "role", "") or "agent"
        req = ClarificationRequest(
            request_id=request_id,
            task_id=task_id,
            agent_role=agent_role,
            fields=fields,
            context=context,
            priority=int(priority),
            timeout_seconds=timeout,
        )
        response = requester.request_clarification(req)
        return response.answers if not response.skipped else {}

    def clarify_blocking(
        self,
        context: str,
        fields: list[ClarificationField],
        timeout: int = 120,
    ) -> dict:
        """Use when the run cannot proceed at all without this answer."""
        return self.clarify(context=context, fields=fields, timeout=timeout, priority=0)

    def _run_without_clarification(self, request: AgentRequest) -> AgentResponse:
        """Re-run with hint to proceed without waiting for user input."""
        hint = "\n\n[Proceed without user clarification; use available information to complete the task.]"
        task = request.task.model_copy(
            update={"description": request.task.description + hint}
        )
        new_request = self.build_request(task)
        return self.run(new_request)

    def _strip_broadcast_and_collect(
        self, task_id: str, text: str
    ) -> tuple[str, list[str]]:
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
            rest = rest[m.end() :].lstrip()
        return (rest, collected)

    def _strip_broadcast_and_emit(self, task: Task, text: str) -> str:
        """If text starts with BROADCAST:, emit to message_bus and strip; return rest."""
        rest, _ = self._strip_broadcast_and_collect(task.id, text or "")
        return rest

    def _store_result_to_memory(self, task: Task, text: str) -> None:
        from devsper.memory.memory_store import MemoryStore
        from devsper.memory.memory_types import MemoryRecord, MemoryType
        from devsper.memory.memory_store import generate_memory_id
        from devsper.memory.memory_index import MemoryIndex

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
        store.store(record, namespace=self.memory_namespace)

    def _run_with_tools_for_request(
        self,
        request: AgentRequest,
        memory_section: str,
        tools_list: list,
    ) -> tuple[str, list[str], list[dict] | None]:
        """Run tool loop for a request; return (result_text, tools_called, tool_calls or None).
        When distributed_tools is True and model returns tool calls, returns tool_calls for controller.
        """
        from devsper.tools.tool_runner import run_tool

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
        if getattr(request, "tool_results", None):
            for tr in request.tool_results:
                name = (tr.get("name") or tr.get("tool_name") or "tool").strip()
                res = tr.get("result") or ""
                conversation.append(f"Tool result ({name}):\n{res}")
        tools_called: list[str] = []
        distributed = getattr(request, "distributed_tools", False)
        for _ in range(self.max_tool_iterations):
            full_prompt = "\n\n".join(conversation)
            response = generate(request.model, full_prompt)
            tool_calls = _parse_all_tool_calls(response)
            if not tool_calls:
                return (response.strip(), tools_called, None)
            for tool_name, _ in tool_calls:
                tools_called.append(tool_name)
            if distributed:
                return (
                    "",
                    tools_called,
                    [{"name": n, "arguments": a} for n, a in tool_calls],
                )
            has_hitl_request = any(n == "hitl.request" for n, _ in tool_calls)
            if has_hitl_request:
                # HITL is blocking and ordering-sensitive; run sequentially.
                conversation.append(f"Response:\n{response}")
                for tool_name, tool_args in tool_calls:
                    if tool_name == "hitl.request":
                        result = self._run_hitl_tool_call(request, tool_args)
                    else:
                        result = run_tool(tool_name, tool_args, task_type=task_type)
                    self._emit_tool_called_audit(task.id, tool_name, result)
                    self._emit(
                        events.TOOL_CALLED,
                        {
                            "task_id": task.id,
                            "tool": tool_name,
                            "result_preview": (result or "")[:200],
                        },
                    )
                    conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
                continue
            if len(tool_calls) == 1 or not self.parallel_tools:
                tool_name, tool_args = tool_calls[0]
                result = run_tool(tool_name, tool_args, task_type=task_type)
                self._emit_tool_called_audit(task.id, tool_name, result)
                self._emit(
                    events.TOOL_CALLED,
                    {
                        "task_id": task.id,
                        "tool": tool_name,
                        "result_preview": (result or "")[:200],
                    },
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
                    {
                        "task_id": task.id,
                        "tool": tool_name,
                        "result_preview": (result or "")[:200],
                    },
                )
                conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
        return (
            conversation[-1].strip() or "Max tool iterations reached.",
            tools_called,
            None,
        )

    def _run_with_tools(
        self,
        task: Task,
        memory_section: str = "",
        role_prefix: str = "",
        model_name: str | None = None,
        tools_list: list | None = None,
        message_bus_section: str = "",
    ) -> str:
        from devsper.tools.selector import get_tools_for_task
        from devsper.tools.tool_runner import run_tool

        model = model_name or self.model_name
        role = getattr(task, "role", None)
        task_type = role or "general"
        if tools_list is not None:
            tools = tools_list
        else:
            score_store = None
            try:
                from devsper.tools.scoring import get_default_score_store

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
            has_hitl_request = any(n == "hitl.request" for n, _ in tool_calls)
            if has_hitl_request:
                conversation.append(f"Response:\n{response}")
                req = AgentRequest(
                    task=task,
                    memory_context=memory_section,
                    tools=[t.name for t in tools],
                    model=model,
                    system_prompt=role_prefix,
                    prefetch_used=False,
                )
                for tool_name, tool_args in tool_calls:
                    if tool_name == "hitl.request":
                        result = self._run_hitl_tool_call(req, tool_args)
                    else:
                        result = run_tool(tool_name, tool_args, task_type=task_type)
                    self._emit_tool_called_audit(task.id, tool_name, result)
                    self._emit(
                        events.TOOL_CALLED,
                        {
                            "task_id": task.id,
                            "tool": tool_name,
                            "result_preview": (result or "")[:200],
                        },
                    )
                    conversation.append(f"Tool result ({tool_name}):\n{result or ''}")
                continue
            if len(tool_calls) == 1 or not self.parallel_tools:
                tool_name, tool_args = tool_calls[0]
                result = run_tool(tool_name, tool_args, task_type=task_type)
                self._emit_tool_called_audit(task.id, tool_name, result)
                self._emit(
                    events.TOOL_CALLED,
                    {
                        "task_id": task.id,
                        "tool": tool_name,
                        "result_preview": (result or "")[:200],
                    },
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
                    {
                        "task_id": task.id,
                        "tool": tool_name,
                        "result_preview": (result or "")[:200],
                    },
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
        from devsper.tools.tool_runner import run_tool

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

    def _run_hitl_tool_call(self, request: AgentRequest, tool_args: dict) -> str:
        requester = getattr(self, "clarification_requester", None)
        if requester is None:
            return json.dumps({"error": "hitl requester unavailable"})

        fields_raw = tool_args.get("fields") or []
        if not isinstance(fields_raw, list) or not fields_raw:
            return json.dumps({"error": "hitl.request requires fields[]"})

        fields: list[ClarificationField] = []
        for f in fields_raw:
            if not isinstance(f, dict):
                continue
            f_type = str(f.get("type") or "text")
            q = str(f.get("question") or "").strip()
            if not q:
                continue
            opts_raw = f.get("options")
            opts = [str(x) for x in opts_raw] if isinstance(opts_raw, list) else None
            default_val = f.get("default")
            default_str = None if default_val is None else str(default_val)
            fields.append(
                ClarificationField(
                    type=f_type,  # type: ignore[arg-type]
                    question=q,
                    options=opts,
                    default=default_str,
                    required=bool(f.get("required", True)),
                )
            )

        if not fields:
            return json.dumps({"error": "hitl.request has no valid fields"})

        req = ClarificationRequest(
            request_id=str(uuid.uuid4()),
            task_id=request.task.id,
            agent_role=getattr(request.task, "role", None) or "agent",
            fields=fields,
            context=str(tool_args.get("context") or "Need user input"),
            priority=int(tool_args.get("priority", 1)),
            timeout_seconds=int(tool_args.get("timeout_seconds", 120)),
        )
        resp = requester.request_clarification(req)
        return json.dumps(
            {
                "request_id": req.request_id,
                "skipped": bool(resp.skipped),
                "answers": resp.answers or {},
            }
        )

    def _emit_tool_called_audit(
        self, task_id: str, tool_name: str, result: str
    ) -> None:
        if not self.audit_logger or not self.audit_run_id:
            return
        try:
            from devsper.audit.logger import make_audit_record

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
            Event(
                timestamp=datetime.now(timezone.utc), type=event_type, payload=payload
            )
        )
