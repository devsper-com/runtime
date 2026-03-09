"""Resolve config: defaults -> user TOML -> project TOML -> env. Apply provider TOML to os.environ."""

import os
from copy import deepcopy

from hivemind.credentials import get_credential
from hivemind.config.config_loader import (
    load_project_config,
    load_user_config,
    normalize_toml_to_flat,
)
from hivemind.config.schema import (
    AgentsConfig,
    BusConfig,
    CacheConfig,
    HivemindConfigModel,
    KnowledgeConfig,
    MemoryConfig,
    ModelsConfig,
    ProviderAzureConfig,
    ProvidersConfig,
    SwarmConfig,
    TelemetryConfig,
    ToolsConfig,
)

_PROVIDER_ENV = {
    "azure_openai": [
        ("endpoint", "AZURE_OPENAI_ENDPOINT"),
        ("api_key", "AZURE_OPENAI_API_KEY"),
        ("deployment_name", "AZURE_OPENAI_DEPLOYMENT_NAME"),
        ("api_version", "AZURE_OPENAI_API_VERSION"),
    ],
    "azure_anthropic": [
        ("endpoint", "AZURE_ANTHROPIC_ENDPOINT"),
        ("api_key", "AZURE_ANTHROPIC_API_KEY"),
        ("deployment_name", "AZURE_ANTHROPIC_DEPLOYMENT_NAME"),
    ],
    "openai": [("api_key", "OPENAI_API_KEY")],
    "anthropic": [("api_key", "ANTHROPIC_API_KEY")],
    "google": [("api_key", "GOOGLE_API_KEY")],
}


def _infer_worker_model_from_env() -> str:
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get(
        "AZURE_OPENAI_API_KEY"
    ):
        return "gpt-5-mini"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get(
        "AZURE_ANTHROPIC_API_KEY"
    ):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


def _infer_planner_model_from_env() -> str:
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get(
        "AZURE_OPENAI_API_KEY"
    ):
        return "gpt-4o"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get(
        "AZURE_ANTHROPIC_API_KEY"
    ):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


def _inject_credentials_from_store() -> None:
    """Inject provider credentials from credential store if not already in env."""
    providers_map = [
        ("openai", "api_key", "OPENAI_API_KEY"),
        ("anthropic", "api_key", "ANTHROPIC_API_KEY"),
        ("github", "token", "GITHUB_TOKEN"),
        ("gemini", "api_key", "GEMINI_API_KEY"),
        ("gemini", "api_key", "GOOGLE_API_KEY"),  # Gemini provider checks both
        ("azure", "api_key", "AZURE_OPENAI_API_KEY"),
        ("azure", "endpoint", "AZURE_OPENAI_ENDPOINT"),
        ("azure", "deployment", "AZURE_OPENAI_DEPLOYMENT_NAME"),
        ("azure", "api_version", "AZURE_OPENAI_API_VERSION"),
        ("azure_anthropic", "api_key", "AZURE_ANTHROPIC_API_KEY"),
        ("azure_anthropic", "endpoint", "AZURE_ANTHROPIC_ENDPOINT"),
        ("azure_anthropic", "deployment", "AZURE_ANTHROPIC_DEPLOYMENT_NAME"),
    ]
    for provider, key, env_var in providers_map:
        if not os.environ.get(env_var):
            val = get_credential(provider, key)
            if val:
                os.environ[env_var] = val


def _apply_provider_toml_to_env(toml_data: dict) -> None:
    """Apply [providers.azure], [azure_openai], etc. to os.environ when not already set."""
    # New format: [providers.azure]
    providers = toml_data.get("providers")
    if isinstance(providers, dict) and "azure" in providers:
        az = providers["azure"]
        if isinstance(az, dict):
            for toml_key, env_key in [
                ("endpoint", "AZURE_OPENAI_ENDPOINT"),
                ("api_key", "AZURE_OPENAI_API_KEY"),
                ("deployment", "AZURE_OPENAI_DEPLOYMENT_NAME"),
                ("api_version", "AZURE_OPENAI_API_VERSION"),
            ]:
                val = az.get(toml_key)
                if val is not None and str(val).strip() and env_key not in os.environ:
                    os.environ[env_key] = str(val).strip()
    # Legacy sections
    for section, mappings in _PROVIDER_ENV.items():
        block = toml_data.get(section)
        if not isinstance(block, dict):
            continue
        for toml_key, env_key in mappings:
            val = block.get(toml_key)
            if val is not None and str(val).strip() and env_key not in os.environ:
                os.environ[env_key] = str(val).strip()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins."""
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _build_merged_raw(
    user_raw: dict,
    project_raw: dict,
) -> dict:
    """Merge user then project (project overrides user). Start from defaults."""
    worker_default = _infer_worker_model_from_env()
    planner_default = _infer_planner_model_from_env()
    defaults: dict = {
        "swarm": {
            "workers": 4,
            "adaptive_planning": False,
            "adaptive_execution": False,
            "max_iterations": 10,
            "speculative_execution": False,
            "cache_enabled": False,
        },
        "agents": {"roles": ["research_agent", "code_agent", "analysis_agent", "critic_agent"]},
        "models": {"planner": planner_default, "worker": worker_default},
        "memory": {"enabled": True, "store_results": True, "top_k": 5},
        "knowledge": {"guide_planning": True, "min_confidence": 0.30, "auto_extract": True},
        "tools": {"enabled": None, "top_k": 0},
        "telemetry": {"enabled": True, "save_events": True},
        "cache": {
            "enabled": True,
            "semantic": False,
            "similarity_threshold": 0.92,
            "max_age_hours": 168.0,
        },
        "bus": {"backend": "memory", "redis_url": "redis://localhost:6379"},
        "events_dir": ".hivemind/events",
        "data_dir": ".hivemind",
        "providers": {
            "azure": {
                "endpoint": "",
                "deployment": "",
                "api_key": "",
                "api_version": "",
            }
        },
    }
    user_norm = normalize_toml_to_flat(user_raw)
    project_norm = normalize_toml_to_flat(project_raw)
    merged = _deep_merge(defaults, user_norm)
    merged = _deep_merge(merged, project_norm)
    return merged


def _apply_env_overrides(merged: dict) -> dict:
    """Apply env vars on top. Priority: env > project > user > defaults."""
    if os.environ.get("HIVEMIND_WORKER_MODEL"):
        merged.setdefault("models", {})["worker"] = os.environ["HIVEMIND_WORKER_MODEL"]
    if os.environ.get("HIVEMIND_PLANNER_MODEL"):
        merged.setdefault("models", {})["planner"] = os.environ[
            "HIVEMIND_PLANNER_MODEL"
        ]
    if os.environ.get("HIVEMIND_EVENTS_DIR"):
        merged["events_dir"] = os.environ["HIVEMIND_EVENTS_DIR"]
    if os.environ.get("HIVEMIND_DATA_DIR"):
        merged["data_dir"] = os.environ["HIVEMIND_DATA_DIR"]
    return merged


def resolve_config(config_path: str | None = None) -> HivemindConfigModel:
    """
    Load user and project config, merge with defaults, apply env.
    If config_path is given, load that file as the only project config (for Swarm(config="path")).
    """
    user_raw = load_user_config()
    if config_path:
        from pathlib import Path
        from hivemind.config.config_loader import _load_toml

        project_raw = _load_toml(Path(config_path))
    else:
        project_raw = load_project_config()

    _apply_provider_toml_to_env(user_raw)
    _apply_provider_toml_to_env(project_raw)

    # Inject credentials from store if not already set in env
    _inject_credentials_from_store()

    merged = _build_merged_raw(user_raw, project_raw)
    merged = _apply_env_overrides(merged)

    # Build Pydantic model
    swarm = SwarmConfig(**(merged.get("swarm") or {}))
    agents = AgentsConfig(**(merged.get("agents") or {}))
    models = ModelsConfig(**(merged.get("models") or {}))
    memory = MemoryConfig(**(merged.get("memory") or {}))
    knowledge = KnowledgeConfig(**(merged.get("knowledge") or {}))
    tools = ToolsConfig(**(merged.get("tools") or {}))
    telemetry = TelemetryConfig(**(merged.get("telemetry") or {}))
    cache = CacheConfig(**(merged.get("cache") or {}))
    bus = BusConfig(**(merged.get("bus") or {}))
    providers_data = merged.get("providers") or {}
    azure_data = providers_data.get("azure") or {}
    providers = ProvidersConfig(azure=ProviderAzureConfig(**azure_data))

    return HivemindConfigModel(
        swarm=swarm,
        agents=agents,
        models=models,
        memory=memory,
        knowledge=knowledge,
        tools=tools,
        telemetry=telemetry,
        cache=cache,
        bus=bus,
        events_dir=merged.get("events_dir", ".hivemind/events"),
        data_dir=merged.get("data_dir", ".hivemind"),
        providers=providers,
    )
