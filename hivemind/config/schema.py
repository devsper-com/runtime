"""Pydantic schema for Hivemind configuration."""

from pydantic import BaseModel, Field


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


class HivemindConfigModel(BaseModel):
    """Full resolved configuration with Pydantic validation."""

    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
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
