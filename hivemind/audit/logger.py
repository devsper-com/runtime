"""
Append-only audit log: JSONL file per run with optional chain integrity.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditRecord:
    """Single append-only audit entry."""
    record_id: str
    timestamp: str
    run_id: str
    task_id: str
    agent_id: str
    event_type: str
    actor: str
    resource: str
    input_hash: str
    output_hash: str
    decision_rationale: str | None = None
    quota_usage: dict | None = None
    pii_detected: bool = False
    pii_redacted: bool = False
    duration_ms: int = 0
    success: bool = True
    prev_record_hash: str = ""

    def to_json_line(self) -> str:
        d = {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "resource": self.resource,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "decision_rationale": self.decision_rationale,
            "quota_usage": self.quota_usage,
            "pii_detected": self.pii_detected,
            "pii_redacted": self.pii_redacted,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "prev_record_hash": self.prev_record_hash,
        }
        return json.dumps(d, sort_keys=True)

    @classmethod
    def from_json_line(cls, line: str) -> "AuditRecord":
        d = json.loads(line)
        return cls(
            record_id=d.get("record_id", ""),
            timestamp=d.get("timestamp", ""),
            run_id=d.get("run_id", ""),
            task_id=d.get("task_id", ""),
            agent_id=d.get("agent_id", ""),
            event_type=d.get("event_type", ""),
            actor=d.get("actor", ""),
            resource=d.get("resource", ""),
            input_hash=d.get("input_hash", ""),
            output_hash=d.get("output_hash", ""),
            decision_rationale=d.get("decision_rationale"),
            quota_usage=d.get("quota_usage"),
            pii_detected=bool(d.get("pii_detected", False)),
            pii_redacted=bool(d.get("pii_redacted", False)),
            duration_ms=int(d.get("duration_ms", 0)),
            success=bool(d.get("success", True)),
            prev_record_hash=d.get("prev_record_hash", ""),
        )


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def make_audit_record(
    run_id: str,
    task_id: str,
    event_type: str,
    actor: str = "",
    resource: str = "",
    input_text: str = "",
    output_text: str = "",
    duration_ms: int = 0,
    success: bool = True,
    pii_detected: bool = False,
    pii_redacted: bool = False,
    agent_id: str = "",
) -> AuditRecord:
    """Build an AuditRecord with hashes; agent_id = node_id + task_id or task_id."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return AuditRecord(
        record_id=str(uuid.uuid4()),
        timestamp=ts,
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id or task_id,
        event_type=event_type,
        actor=actor,
        resource=resource,
        input_hash=_sha256(input_text),
        output_hash=_sha256(output_text),
        pii_detected=pii_detected,
        pii_redacted=pii_redacted,
        duration_ms=duration_ms,
        success=success,
    )


class AuditLogger:
    """Write-once append-only audit log. Backend: JSONL file under data_dir/audit/{run_id}.audit.jsonl."""

    def __init__(self, data_dir: str, run_id: str = "") -> None:
        self.data_dir = data_dir
        self.run_id = run_id
        self._audit_dir = os.path.join(data_dir, "audit")
        self._last_hash: str = ""
        self._file_path: str | None = None

    def _path(self, run_id: str) -> str:
        return os.path.join(self._audit_dir, f"{run_id or self.run_id}.audit.jsonl")

    def _ensure_chain(self, path: str) -> None:
        """Load last line hash from file so chain continues."""
        if self._file_path == path:
            return
        self._file_path = path
        self._last_hash = ""
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._last_hash = _sha256(line)
            except Exception:
                pass

    def log(self, record: AuditRecord) -> None:
        """Append one record to the run's audit file. Permissions 0o600."""
        run_id = record.run_id or self.run_id
        if not run_id:
            return
        path = self._path(run_id)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_chain(path)
        record.prev_record_hash = self._last_hash
        line = record.to_json_line()
        self._last_hash = _sha256(line)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass

    def export(self, run_id: str, format: str = "jsonl") -> str:
        """Return formatted export for compliance (jsonl, csv, siem)."""
        path = self._path(run_id)
        if not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        records = [AuditRecord.from_json_line(ln) for ln in lines]
        if format == "jsonl":
            return "\n".join(r.to_json_line() for r in records)
        if format == "csv":
            headers = [
                "record_id", "timestamp", "run_id", "task_id", "event_type",
                "actor", "resource", "success", "duration_ms", "pii_detected", "pii_redacted",
            ]
            rows = [
                ",".join(
                    str(getattr(r, h, "")).replace(",", ";")
                    for h in headers
                )
                for r in records
            ]
            return ",".join(headers) + "\n" + "\n".join(rows)
        if format == "siem":
            return json.dumps([r.to_json_line() for r in records])
        return "\n".join(r.to_json_line() for r in records)

    @staticmethod
    def verify(run_id: str, data_dir: str) -> tuple[bool, str]:
        """
        Verify chain integrity: each record's prev_record_hash must match previous line hash.
        Return (ok, message).
        """
        audit_dir = os.path.join(data_dir, "audit")
        path = os.path.join(audit_dir, f"{run_id}.audit.jsonl")
        if not os.path.isfile(path):
            return False, "Audit file not found"
        prev_hash = ""
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                rec = AuditRecord.from_json_line(line)
                expected = _sha256(line)
                if rec.prev_record_hash != prev_hash:
                    return False, f"Chain break at record {i}: prev_record_hash mismatch"
                prev_hash = expected
        return True, "Chain intact"
