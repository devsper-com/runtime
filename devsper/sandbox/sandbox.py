"""
AgentSandbox: wraps agent execution with resource quotas and isolation.

Enforces: allowed_tool_categories, max_tool_calls, max_output_tokens;
tracks usage (wall time, tool calls, tokens).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from devsper.agents.agent import Agent, AgentRequest, AgentResponse

if TYPE_CHECKING:
    from devsper.config.schema import SandboxConfig


@dataclass
class ResourceQuota:
    """Limits and permissions for a sandboxed run."""
    max_memory_mb: int = 512
    max_cpu_seconds: int = 60
    max_tool_calls: int = 20
    max_output_tokens: int = 4096
    allowed_tool_categories: list[str] | None = None  # None = all
    blocked_tool_categories: list[str] = field(default_factory=list)
    network_access: bool = True
    filesystem_write: bool = False


class SandboxQuotaExceeded(Exception):
    """Raised when a quota limit is exceeded."""

    def __init__(self, quota_type: str, limit: int | float, actual: int | float) -> None:
        self.quota_type = quota_type
        self.limit = limit
        self.actual = actual
        super().__init__(f"Sandbox quota exceeded: {quota_type} (limit={limit}, actual={actual})")


def _get_tool_categories(tool_name: str) -> list[str]:
    """Return categories for a tool (from registry if available)."""
    try:
        from devsper.tools.registry import get
        t = get(tool_name)
        if t is not None and getattr(t, "category", None):
            return [t.category]
    except Exception:
        pass
    return []


def _filter_tools_by_quota(tool_names: list[str], quota: ResourceQuota) -> list[str]:
    """Return tool names that are allowed by quota."""
    if quota.allowed_tool_categories is None and not quota.blocked_tool_categories:
        return list(tool_names)
    out = []
    for name in tool_names:
        cats = _get_tool_categories(name)
        if quota.blocked_tool_categories and any(c in quota.blocked_tool_categories for c in cats):
            continue
        if quota.allowed_tool_categories is not None and cats:
            if not any(c in quota.allowed_tool_categories for c in cats):
                continue
        out.append(name)
    return out


class AgentSandbox:
    """Wraps agent execution with resource quotas. Use run(request, quota) -> AgentResponse."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    def run(self, request: AgentRequest, quota: ResourceQuota) -> AgentResponse:
        """
        Run the agent with quota enforcement: filter tools, enforce max_tool_calls and max_output_tokens.
        Tracks usage and includes it in AgentResponse (via agent's response; we add quota_usage if needed).
        """
        filtered_tools = _filter_tools_by_quota(request.tools, quota)
        req = AgentRequest(
            task=request.task,
            memory_context=request.memory_context,
            tools=filtered_tools,
            model=request.model,
            system_prompt=request.system_prompt,
            prefetch_used=request.prefetch_used,
        )
        tool_call_count = [0]
        max_tool_calls = quota.max_tool_calls
        max_output_tokens = quota.max_output_tokens

        from devsper.tools.tool_runner import run_tool as _run_tool_impl

        def counting_run_tool(name: str, args: dict, task_type: str | None = None):
            tool_call_count[0] += 1
            if tool_call_count[0] > max_tool_calls:
                raise SandboxQuotaExceeded("max_tool_calls", max_tool_calls, tool_call_count[0])
            return _run_tool_impl(name, args, task_type=task_type)

        try:
            with _patch_tool_runner(counting_run_tool):
                response = self.agent.run(req)
        except SandboxQuotaExceeded:
            raise

        result = response.result or ""
        if max_output_tokens and len(result) > max_output_tokens:
            result = result[:max_output_tokens] + "\n\n[Output truncated: max_output_tokens exceeded.]"
        return AgentResponse(
            task_id=response.task_id,
            result=result,
            tools_called=response.tools_called,
            broadcasts=response.broadcasts,
            tokens_used=response.tokens_used,
            duration_seconds=response.duration_seconds,
            error=response.error,
            success=response.success,
        )


def get_quota_for_role(sandbox_config: "SandboxConfig", role: str | None) -> ResourceQuota:
    """Build ResourceQuota for a role from sandbox config (defaults + role overrides)."""
    role = (role or "").strip()
    q = ResourceQuota(
        max_memory_mb=sandbox_config.default_max_memory_mb,
        max_cpu_seconds=sandbox_config.default_max_cpu_seconds,
        max_tool_calls=sandbox_config.default_max_tool_calls,
        max_output_tokens=4096,
    )
    for r in sandbox_config.roles or []:
        if (r.role or "").strip() == role:
            if r.max_tool_calls is not None:
                q.max_tool_calls = r.max_tool_calls
            if r.allowed_tool_categories is not None:
                q.allowed_tool_categories = r.allowed_tool_categories
            if r.blocked_tool_categories:
                q.blocked_tool_categories = list(r.blocked_tool_categories)
            if r.filesystem_write:
                q.filesystem_write = True
            break
    return q


class _patch_tool_runner:
    """Temporarily patch the tool runner so we can count calls."""

    def __init__(self, replacement):
        self.replacement = replacement
        self.orig = None

    def __enter__(self):
        import devsper.tools.tool_runner as tr
        self.orig = getattr(tr, "run_tool", None)
        tr.run_tool = self.replacement
        return self

    def __exit__(self, *args):
        import devsper.tools.tool_runner as tr
        if self.orig is not None:
            tr.run_tool = self.orig
        return False
