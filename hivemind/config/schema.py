"""Pydantic schema for Hivemind configuration."""

from pydantic import BaseModel, Field


class SwarmConfig(BaseModel):
    workers: int = 4
    adaptive_planning: bool = False
    max_iterations: int = 10


class ModelsConfig(BaseModel):
    planner: str = "mock"
    worker: str = "mock"


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
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
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
