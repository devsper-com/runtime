"""
Canonical `event_type` strings accepted by the platform runtime ingest API and
emitted by the runtime forwarder.

**Single source of truth for Python.** Mirror:
`platform/services/api/internal/contracts/runtime_events.go`
"""

from __future__ import annotations


class PlatformEventType:
    """Platform SSE / run_events.event_type values (string constants only)."""

    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    RUN_PROGRESS = "run_progress"
    TOOL_CALLED = "tool_called"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    CLARIFICATION_REQUESTED = "clarification_requested"
    CLARIFICATION_ANSWERED = "clarification_answered"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    LOG = "log"
    EXECUTION_GRAPH_UPDATED = "EXECUTION_GRAPH_UPDATED"
    SPECULATIVE_TASK_STARTED = "SPECULATIVE_TASK_STARTED"
    SPECULATIVE_TASK_CANCELLED = "SPECULATIVE_TASK_CANCELLED"
    HITL_REQUESTED = "HITL_REQUESTED"
    HITL_RESOLVED = "HITL_RESOLVED"
    WORKER_ASSIGNED = "WORKER_ASSIGNED"
    AGENT_POOL_USED = "AGENT_POOL_USED"
    EXECUTOR_FINISHED = "executor_finished"


# DevSper `events` enum value (as string) -> platform ingest type
DEVSPER_TO_PLATFORM: dict[str, str] = {
    "swarm_started": PlatformEventType.RUN_STARTED,
    "executor_started": PlatformEventType.RUN_STARTED,
    "task_started": PlatformEventType.STEP_STARTED,
    "task_completed": PlatformEventType.STEP_COMPLETED,
    "agent_started": PlatformEventType.AGENT_STARTED,
    "agent_finished": PlatformEventType.AGENT_FINISHED,
    "run_completed": PlatformEventType.RUN_COMPLETED,
    "task_failed": PlatformEventType.RUN_FAILED,
    "run_failed": PlatformEventType.RUN_FAILED,
    "tool_called": PlatformEventType.TOOL_CALLED,
    "clarification_requested": PlatformEventType.CLARIFICATION_REQUESTED,
    "clarification_needed": PlatformEventType.CLARIFICATION_REQUESTED,
    "clarification_received": PlatformEventType.CLARIFICATION_ANSWERED,
    "planner_started": PlatformEventType.RUN_PROGRESS,
    "planner_finished": PlatformEventType.RUN_PROGRESS,
    "reasoning_node_added": PlatformEventType.RUN_PROGRESS,
    "budget_warning": PlatformEventType.RUN_PROGRESS,
    "task_created": PlatformEventType.RUN_PROGRESS,
    "task_model_selected": PlatformEventType.RUN_PROGRESS,
    "agent_broadcast": PlatformEventType.RUN_PROGRESS,
    "run_manifest_emitted": PlatformEventType.RUN_PROGRESS,
    "worker_assigned": PlatformEventType.WORKER_ASSIGNED,
    "speculative_started": PlatformEventType.SPECULATIVE_TASK_STARTED,
    "speculative_cancelled": PlatformEventType.SPECULATIVE_TASK_CANCELLED,
    "hitl_requested": PlatformEventType.HITL_REQUESTED,
    "hitl_resolved": PlatformEventType.HITL_RESOLVED,
    "executor_finished": PlatformEventType.EXECUTOR_FINISHED,
}
