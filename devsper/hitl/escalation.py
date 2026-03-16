"""
Escalation policies and triggers: when to send a task for human approval.
"""

from dataclasses import dataclass
from typing import Literal

# Avoid circular import; Task, AgentResponse, DecisionRecord used at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from devsper.types.task import Task
    from devsper.agents.agent import AgentResponse
    from devsper.explainability.decision_tree import DecisionRecord


EscalationTriggerType = Literal[
    "confidence_below",
    "cost_above",
    "tool_category",
    "keyword_match",
    "critic_score_below",
    "sla_at_risk",
]


@dataclass
class EscalationTrigger:
    type: EscalationTriggerType
    threshold: float | str  # number for numeric triggers, string for keyword/category


@dataclass
class EscalationPolicy:
    triggers: list[EscalationTrigger]
    approvers: list[str]  # email://, slack://, webhook://
    timeout_seconds: int = 3600
    on_timeout: Literal["auto_approve", "auto_reject", "escalate_further"] = "auto_approve"


class EscalationChecker:
    """Evaluate task + response + decision against configured triggers; return first match or None."""

    def __init__(self, policies: list[EscalationPolicy]) -> None:
        self.policies = policies
        self._triggers: list[tuple[EscalationTrigger, EscalationPolicy]] = []
        for p in policies:
            for t in p.triggers:
                self._triggers.append((t, p))

    def evaluate(
        self,
        task: "Task",
        response: "AgentResponse",
        decision: "DecisionRecord | None",
    ) -> tuple[EscalationTrigger, EscalationPolicy] | None:
        """Check all configured triggers. Return first (trigger, policy) match or None."""
        for trigger, policy in self._triggers:
            if self._matches(trigger, task, response, decision):
                return (trigger, policy)
        return None

    def _matches(
        self,
        trigger: EscalationTrigger,
        task: "Task",
        response: "AgentResponse",
        decision: "DecisionRecord | None",
    ) -> bool:
        t = trigger.type
        th = trigger.threshold
        if t == "confidence_below" and decision is not None:
            return (decision.confidence or 0) < float(th)
        if t == "cost_above":
            # Approximate cost from tokens if available
            cost = 0.0
            if getattr(response, "tokens_used", None):
                cost = (response.tokens_used or 0) * 1e-6  # rough
            return cost > float(th)
        if t == "tool_category":
            tools = getattr(response, "tools_called", []) or []
            # Compare category names if we had a category; use tool names as proxy
            return isinstance(th, str) and th.lower() in [str(x).lower() for x in tools]
        if t == "keyword_match" and isinstance(th, str):
            text = (task.description or "") + " " + (response.result or "")
            return th.lower() in text.lower()
        if t == "critic_score_below" and decision is not None:
            score = decision.critic_score
            if score is not None:
                return score < float(th)
            return False
        if t == "sla_at_risk":
            # Would need SLA context; treat as no match if not applicable
            return False
        return False
