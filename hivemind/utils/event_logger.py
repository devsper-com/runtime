from datetime import datetime, timezone
import os
from hivemind.types.event import Event


class EventLog:
    def __init__(self, events_folder_path: str = ".hivemind/events"):
        os.makedirs(events_folder_path, exist_ok=True)
        self.log_path = os.path.join(events_folder_path, f"events_{datetime.now(timezone.utc)}.jsonl")

    def append_event(self, event: Event) -> None:
        with open(self.log_path, "a") as f:
            f.write(event.model_dump_json() + "\n")

    def read_events(self) -> list[Event]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path, "r") as f:
            return [Event.model_validate_json(line) for line in f if line.strip()]

    def clear(self) -> None:
        if os.path.exists(self.log_path):
            os.remove(self.log_path)