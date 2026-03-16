"""
devsper configuration: TOML + env, Pydantic-validated.

Priority: env > project config > user config > defaults.
Config locations: ./devsper.toml, ./workflow.devsper.toml, ~/.config/devsper/config.toml,
and legacy .devsper/config.toml.
"""

from devsper.config.resolver import resolve_config
from devsper.config.schema import (
    A2AConfig,
    devsperConfigModel,
    KnowledgeConfig,
    MCPConfig,
    MemoryConfig,
    ModelsConfig,
    NodesConfig,
    ProviderAzureConfig,
    ProvidersConfig,
    SwarmConfig,
    TelemetryConfig,
    ToolsConfig,
)

# Backward compatibility: old code expects devsperConfig and get_config()
devsperConfig = devsperConfigModel


def get_config(config_path: str | None = None) -> devsperConfigModel:
    """
    Load and resolve configuration.
    Returns object with .worker_model, .planner_model, .events_dir, .data_dir,
    and .swarm, .models, .memory, .tools, .telemetry, .providers.
    """
    return resolve_config(config_path=config_path)


__all__ = [
    "A2AConfig",
    "get_config",
    "devsperConfig",
    "devsperConfigModel",
    "KnowledgeConfig",
    "MCPConfig",
    "MemoryConfig",
    "ModelsConfig",
    "ProviderAzureConfig",
    "ProvidersConfig",
    "SwarmConfig",
    "TelemetryConfig",
    "ToolsConfig",
]
