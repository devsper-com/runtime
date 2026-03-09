"""Bus message: serializable pub/sub payload."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class BusMessage:
    id: str
    topic: str
    payload: dict
    sender_id: str
    timestamp: str
    run_id: str

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
        })

    @classmethod
    def from_json(cls, raw: str) -> "BusMessage":
        data = json.loads(raw)
        return cls(
            id=data["id"],
            topic=data["topic"],
            payload=dict(data.get("payload", {})),
            sender_id=data.get("sender_id", "local"),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            run_id=data.get("run_id", ""),
        )


def create_bus_message(
    topic: str,
    payload: dict,
    *,
    sender_id: str = "local",
    run_id: str = "",
) -> BusMessage:
    """Create a BusMessage with generated id and current timestamp."""
    return BusMessage(
        id=str(uuid4()),
        topic=topic,
        payload=payload,
        sender_id=sender_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
    )
