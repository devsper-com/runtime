"""
Approval store and notifier: persist pending approvals, notify approvers, resolve (approve/reject).
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from hivemind.hitl.escalation import EscalationPolicy, EscalationTrigger


@dataclass
class ApprovalRequest:
    request_id: str
    task: object  # Task
    proposed_result: str
    decision_record: object | None  # DecisionRecord
    trigger: EscalationTrigger
    created_at: str
    expires_at: str
    status: Literal["pending", "approved", "rejected", "timeout"] = "pending"
    reviewer_notes: str | None = None

    def to_dict(self) -> dict:
        task = self.task
        task_dict = getattr(task, "to_dict", lambda: {"id": getattr(task, "id", ""), "description": getattr(task, "description", "")})()
        dr = self.decision_record
        dr_dict = None
        if dr is not None and hasattr(dr, "__dict__"):
            dr_dict = {"task_id": getattr(dr, "task_id", ""), "critic_score": getattr(dr, "critic_score", None), "confidence": getattr(dr, "confidence", 0)}
        return {
            "request_id": self.request_id,
            "task": task_dict,
            "proposed_result": self.proposed_result,
            "decision_record": dr_dict,
            "trigger": {"type": self.trigger.type, "threshold": self.trigger.threshold},
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "reviewer_notes": self.reviewer_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRequest":
        from hivemind.types.task import Task
        task_data = data.get("task") or {}
        task = Task.from_dict(task_data) if isinstance(task_data, dict) else task_data
        tr = data.get("trigger") or {}
        trigger = EscalationTrigger(type=tr.get("type", "confidence_below"), threshold=tr.get("threshold", 0.5))
        return cls(
            request_id=data.get("request_id", ""),
            task=task,
            proposed_result=data.get("proposed_result", ""),
            decision_record=data.get("decision_record"),
            trigger=trigger,
            created_at=data.get("created_at", ""),
            expires_at=data.get("expires_at", ""),
            status=data.get("status", "pending"),
            reviewer_notes=data.get("reviewer_notes"),
        )


class ApprovalStore:
    """Persist pending approvals under {data_dir}/approvals/{request_id}.json."""

    def __init__(self, data_dir: str = ".hivemind") -> None:
        self.data_dir = data_dir
        self._approvals_dir = os.path.join(data_dir, "approvals")
        os.makedirs(self._approvals_dir, exist_ok=True)

    def _path(self, request_id: str) -> str:
        return os.path.join(self._approvals_dir, f"{request_id}.json")

    def list_pending(self) -> list[ApprovalRequest]:
        """Return all pending approval requests."""
        out: list[ApprovalRequest] = []
        for name in os.listdir(self._approvals_dir):
            if name.endswith(".json"):
                rid = name[:-5]
                req = self.get(rid)
                if req is not None and req.status == "pending":
                    out.append(req)
        return out

    def get(self, request_id: str) -> ApprovalRequest | None:
        """Load one request by id."""
        path = self._path(request_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ApprovalRequest.from_dict(json.load(f))
        except Exception:
            return None

    def save(self, request: ApprovalRequest) -> None:
        """Write request to disk."""
        path = self._path(request.request_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request.to_dict(), f, indent=0)

    def resolve(self, request_id: str, approved: bool, notes: str = "") -> None:
        """Mark request approved or rejected and save."""
        req = self.get(request_id)
        if req is None:
            return
        req.status = "approved" if approved else "rejected"
        req.reviewer_notes = notes or req.reviewer_notes
        self.save(req)


class ApprovalNotifier:
    """Send approval requests via configured channels (webhook, slack, email)."""

    async def notify(self, request: ApprovalRequest, policy: EscalationPolicy) -> None:
        """For each approver in policy.approvers, parse scheme and dispatch."""
        for approver in policy.approvers or []:
            if approver.startswith("webhook://"):
                await self._notify_webhook(request, approver[10:].strip())
            elif approver.startswith("slack://"):
                await self._notify_slack(request, approver[8:].strip())
            elif approver.startswith("email://"):
                self._notify_email(request, approver[8:].strip())

    async def _notify_webhook(self, request: ApprovalRequest, url: str) -> None:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(url, json=request.to_dict(), timeout=10.0)
        except Exception as e:
            import sys
            print(f"[hitl] webhook notification failed: {e}", file=sys.stderr)

    async def _notify_slack(self, request: ApprovalRequest, webhook_or_channel: str) -> None:
        try:
            import httpx
            payload = {
                "text": f"Approval requested: {getattr(request.task, 'description', '')[:200]}...",
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*Task:* {getattr(request.task, 'description', '')[:300]}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*Request ID:* `{request.request_id}`"}},
                ],
            }
            if webhook_or_channel.startswith("http"):
                async with httpx.AsyncClient() as client:
                    await client.post(webhook_or_channel, json=payload, timeout=10.0)
            else:
                import sys
                print("[hitl] slack:// URL must be webhook URL (https://hooks.slack.com/...)", file=sys.stderr)
        except Exception as e:
            import sys
            print(f"[hitl] slack notification failed: {e}", file=sys.stderr)

    def _notify_email(self, request: ApprovalRequest, _address: str) -> None:
        import sys
        print("[hitl] email notifications require external SMTP config; printing to stdout", file=sys.stderr)
        print(f"Approval requested: request_id={request.request_id} task={getattr(request.task, 'description', '')[:100]}")
