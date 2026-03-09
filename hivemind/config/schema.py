"""Pydantic schema for Hivemind configuration."""

from typing import Literal

from pydantic import BaseModel, Field


class BusConfig(BaseModel):
    """v1.9: message bus backend (memory or redis)."""
    backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379"


class SwarmConfig(BaseModel):
    workers: int = 4
    adaptive_planning: bool = False
    adaptive_execution: bool = False  # v1.2: real-time adaptation (slow/failed task handling)
    max_iterations: int = 10
    speculative_execution: bool = False
    cache_enabled: bool = False
    parallel_tools: bool = True  # v1.6: run independent tool calls in parallel within agents
    # v1.7
    critic_enabled: bool = True
    critic_threshold: float = 0.70
    critic_roles: list[str] = ["research", "analysis", "code"]
    message_bus_enabled: bool = True
    prefetch_enabled: bool = True
    prefetch_max_age_seconds: float = 30.0
    # v1.9
    checkpoint_interval: int = 10
    checkpoint_enabled: bool = True


class CacheConfig(BaseModel):
    """v1.6: cache section for semantic task cache."""
    enabled: bool = True
    semantic: bool = False
    similarity_threshold: float = 0.92
    max_age_hours: float = 168.0  # 1 week


class AgentsConfig(BaseModel):
    """Agent roles enabled for the swarm (research, analysis, critic, code)."""
    roles: list[str] = ["research_agent", "code_agent", "analysis_agent", "critic_agent"]


class ModelsConfig(BaseModel):
    planner: str = "mock"
    worker: str = "mock"
    fast: str | None = None  # v1.6: simple tier (e.g. haiku/flash)
    quality: str | None = None  # v1.6: complex tier (defaults to planner)


class MemoryConfig(BaseModel):
    enabled: bool = True
    store_results: bool = True
    top_k: int = 5


class KnowledgeConfig(BaseModel):
    """v1.8: knowledge-guided planning and auto-extraction."""
    guide_planning: bool = True
    min_confidence: float = 0.30
    auto_extract: bool = True


class ToolsConfig(BaseModel):
    enabled: list[str] | None = None  # None = all categories
    top_k: int = 0  # 0 = no limit


class TelemetryConfig(BaseModel):
    enabled: bool = True
    save_events: bool = True


class ProviderAzureConfig(BaseModel):
    endpoint: str = ""
    deployment: str = ""
    api_key: str = ""
    api_version: str = ""


class ProvidersConfig(BaseModel):
    azure: ProviderAzureConfig = Field(default_factory=ProviderAzureConfig)


class NodesConfig(BaseModel):
    """v1.10: distributed node mode and RPC."""
    mode: Literal["single", "distributed"] = "single"
    role: Literal["controller", "worker", "hybrid"] = "hybrid"
    rpc_port: int = 7700
    rpc_token: str | None = None
    max_workers_per_node: int = 8
    node_tags: list[str] = Field(default_factory=list)
    controller_url: str = "http://localhost:7700"
    heartbeat_interval_seconds: float = 10.0
    task_claim_timeout_seconds: int = 120


class HivemindConfigModel(BaseModel):
    """Full resolved configuration with Pydantic validation."""

    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    bus: BusConfig = Field(default_factory=BusConfig)
    nodes: NodesConfig = Field(default_factory=NodesConfig)
    events_dir: str = ".hivemind/events"
    data_dir: str = ".hivemind"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)

    # Backward-compat aliases (property-style access from old HivemindConfig)
    @property
    def worker_model(self) -> str:
        return self.models.worker

    @property
    def planner_model(self) -> str:
        return self.models.planner
