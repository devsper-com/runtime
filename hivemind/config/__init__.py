"""
Hivemind configuration: TOML + env, Pydantic-validated.

Priority: env > project config > user config > defaults.
Config locations: ./hivemind.toml, ./workflow.hivemind.toml, ~/.config/hivemind/config.toml,
and legacy .hivemind/config.toml.
"""

from hivemind.config.resolver import resolve_config
from hivemind.config.schema import (
    A2AConfig,
    HivemindConfigModel,
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

# Backward compatibility: old code expects HivemindConfig and get_config()
HivemindConfig = HivemindConfigModel


def get_config(config_path: str | None = None) -> HivemindConfigModel:
    """
    Load and resolve configuration.
    Returns object with .worker_model, .planner_model, .events_dir, .data_dir,
    and .swarm, .models, .memory, .tools, .telemetry, .providers.
    """
    return resolve_config(config_path=config_path)


__all__ = [
    "A2AConfig",
    "get_config",
    "HivemindConfig",
    "HivemindConfigModel",
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
