from typing import Literal, get_args
from pydantic import BaseModel, Field

ModelName = Literal[
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-sonnet-3-7-20250219",
    "claude-haiku-3-5-20241022",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4o",
    "o3",
    "o3-pro",
    "o4-mini",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

available_models: list[str] = list(get_args(ModelName))

DEFAULT_WORKER_MODEL: ModelName = "claude-haiku-4-5-20251001"
DEFAULT_PLANNER_MODEL: ModelName = "claude-opus-4-6"


class Swarm(BaseModel):
    worker_count: int
    worker_model: ModelName = DEFAULT_WORKER_MODEL
    planner_model: ModelName = DEFAULT_PLANNER_MODEL
    models: list[str] = Field(default_factory=lambda: list(get_args(ModelName)))
