"""Language-agnostic HTTP protocol schema for remote agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentExecuteContext(BaseModel):
    memory: list[dict] = Field(default_factory=list)
    prior_outputs: dict = Field(default_factory=dict)
    tools_available: list[str] = Field(default_factory=list)


class AgentExecuteConfig(BaseModel):
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.7


class AgentExecuteRequest(BaseModel):
    task_id: str
    run_id: str
    task: str
    context: AgentExecuteContext = Field(default_factory=AgentExecuteContext)
    config: AgentExecuteConfig = Field(default_factory=AgentExecuteConfig)
    budget_remaining_usd: float | None = None


class ToolCallRecord(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
    result: str | dict | None = None


class AgentExecuteTokens(BaseModel):
    prompt: int = 0
    completion: int = 0


class AgentExecuteResponse(BaseModel):
    task_id: str
    output: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    tokens: AgentExecuteTokens = Field(default_factory=AgentExecuteTokens)
    cost_usd: float | None = None
    duration_ms: int = 0
    error: str | None = None
