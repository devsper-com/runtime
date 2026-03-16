"""Default configuration values for devsper."""

from devsper.config.schema import (
    MemoryConfig,
    ModelsConfig,
    ProviderAzureConfig,
    SwarmConfig,
    TelemetryConfig,
    ToolsConfig,
)


def get_swarm_defaults() -> SwarmConfig:
    return SwarmConfig(
        workers=4,
        adaptive_planning=False,
        max_iterations=10,
    )


def get_models_defaults(worker_model: str = "mock", planner_model: str = "mock") -> ModelsConfig:
    return ModelsConfig(
        planner=planner_model,
        worker=worker_model,
    )


def get_memory_defaults() -> MemoryConfig:
    return MemoryConfig(
        enabled=True,
        store_results=True,
        top_k=5,
    )


def get_tools_defaults() -> ToolsConfig:
    return ToolsConfig(
        enabled=None,  # None = all categories
        top_k=0,  # 0 = no limit, use all tools
    )


def get_telemetry_defaults() -> TelemetryConfig:
    return TelemetryConfig(
        enabled=True,
        save_events=True,
    )


def get_provider_azure_defaults() -> ProviderAzureConfig:
    return ProviderAzureConfig(
        endpoint="",
        deployment="",
        api_key="",
        api_version="",
    )


def get_full_defaults(
    worker_model: str = "mock",
    planner_model: str = "mock",
    events_dir: str = ".devsper/events",
    data_dir: str = ".devsper",
) -> dict:
    """Raw defaults for merging. Used by resolver."""
    return {
        "swarm": get_swarm_defaults().model_dump(),
        "models": get_models_defaults(worker_model, planner_model).model_dump(),
        "memory": get_memory_defaults().model_dump(),
        "tools": get_tools_defaults().model_dump(),
        "telemetry": get_telemetry_defaults().model_dump(),
        "events_dir": events_dir,
        "data_dir": data_dir,
        "providers": {
            "azure": get_provider_azure_defaults().model_dump(),
        },
    }
