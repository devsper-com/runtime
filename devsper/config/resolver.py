"""Resolve config: defaults -> user TOML -> project TOML -> env. Apply provider TOML to os.environ."""

import os
from copy import deepcopy

from devsper.credentials import inject_into_env
from devsper.config.config_loader import (
    load_project_config,
    load_user_config,
    normalize_toml_to_flat,
)
from devsper.config.schema import (
    AgentsConfig,
    A2AConfig,
    A2AAgentConfig,
    BusConfig,
    CacheConfig,
    HitlConfig,
    HitlPolicyConfig,
    HitlTriggerConfig,
    devsperConfigModel,
    KnowledgeConfig,
    MCPConfig,
    MCPServerConfig,
    MemoryConfig,
    ModelsConfig,
    NodesConfig,
    ProviderAzureConfig,
    ProviderOllamaConfig,
    ProviderVLLMConfig,
    ProviderCustomConfig,
    ProvidersConfig,
    SandboxConfig,
    SandboxRoleConfig,
    ComplianceConfig,
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
        "nodes": {
            "mode": "single",
            "role": "hybrid",
            "run_id": None,
            "rpc_port": 7700,
            "rpc_token": None,
            "max_workers_per_node": 8,
            "node_tags": [],
            "controller_url": "http://localhost:7700",
            "heartbeat_interval_seconds": 10.0,
            "task_claim_timeout_seconds": 120,
        },
        "events_dir": ".devsper/events",
        "data_dir": ".devsper",
        "mcp": {"servers": []},
        "a2a": {"agents": [], "serve": False, "serve_port": 8080},
        "hitl": {"enabled": False, "policies": []},
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
    if os.environ.get("DEVSPER_WORKER_MODEL"):
        merged.setdefault("models", {})["worker"] = os.environ["DEVSPER_WORKER_MODEL"]
    if os.environ.get("DEVSPER_PLANNER_MODEL"):
        merged.setdefault("models", {})["planner"] = os.environ[
            "DEVSPER_PLANNER_MODEL"
        ]
    if os.environ.get("DEVSPER_EVENTS_DIR"):
        merged["events_dir"] = os.environ["DEVSPER_EVENTS_DIR"]
    if os.environ.get("DEVSPER_DATA_DIR"):
        merged["data_dir"] = os.environ["DEVSPER_DATA_DIR"]
    return merged


def resolve_config(config_path: str | None = None) -> devsperConfigModel:
    """
    Load user and project config, merge with defaults, apply env.
    If config_path is given, load that file as the only project config (for Swarm(config="path")).
    """
    user_raw = load_user_config()
    if config_path:
        from pathlib import Path
        from devsper.config.config_loader import _load_toml

        project_raw = _load_toml(Path(config_path))
    else:
        project_raw = load_project_config()

    _apply_provider_toml_to_env(user_raw)
    _apply_provider_toml_to_env(project_raw)

    # Inject credentials from store if not already set in env
    inject_into_env()

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
    nodes = NodesConfig(**(merged.get("nodes") or {}))
    # MCP: [[mcp.servers]] -> list of MCPServerConfig
    mcp_data = merged.get("mcp") or {}
    mcp_servers = mcp_data.get("servers") if isinstance(mcp_data, dict) else []
    if not isinstance(mcp_servers, list):
        mcp_servers = []
    mcp = MCPConfig(servers=[MCPServerConfig(**s) for s in mcp_servers if isinstance(s, dict)])
    # A2A: [[a2a.agents]] and [a2a] serve/serve_port
    a2a_data = merged.get("a2a") or {}
    a2a_agents = a2a_data.get("agents") if isinstance(a2a_data, dict) else []
    if not isinstance(a2a_agents, list):
        a2a_agents = []
    a2a = A2AConfig(
        agents=[A2AAgentConfig(**a) for a in a2a_agents if isinstance(a, dict)],
        serve=bool(a2a_data.get("serve", False)) if isinstance(a2a_data, dict) else False,
        serve_port=int(a2a_data.get("serve_port", 8080)) if isinstance(a2a_data, dict) else 8080,
    )
    providers_data = merged.get("providers") or {}
    azure_data = providers_data.get("azure") or {}
    ollama_data = providers_data.get("ollama") or {}
    vllm_data = providers_data.get("vllm") or {}
    custom_data = providers_data.get("custom") or {}
    fallback_block = providers_data.get("fallback_order") or {}
    fallback_order = (
        fallback_block.get("order")
        if isinstance(fallback_block, dict)
        else fallback_block
    )
    if not isinstance(fallback_order, list):
        fallback_order = []
    providers = ProvidersConfig(
        azure=ProviderAzureConfig(**azure_data),
        ollama=ProviderOllamaConfig(**(ollama_data if isinstance(ollama_data, dict) else {})),
        vllm=ProviderVLLMConfig(**(vllm_data if isinstance(vllm_data, dict) else {})),
        custom=ProviderCustomConfig(**(custom_data if isinstance(custom_data, dict) else {})),
        fallback_order=fallback_order,
    )
    sandbox_data = merged.get("sandbox") or {}
    sandbox_roles = sandbox_data.get("roles") if isinstance(sandbox_data, dict) else []
    if not isinstance(sandbox_roles, list):
        sandbox_roles = []
    sandbox = SandboxConfig(
        enabled=bool(sandbox_data.get("enabled", True)) if isinstance(sandbox_data, dict) else True,
        default_max_memory_mb=int(sandbox_data.get("default_max_memory_mb", 512)) if isinstance(sandbox_data, dict) else 512,
        default_max_cpu_seconds=int(sandbox_data.get("default_max_cpu_seconds", 60)) if isinstance(sandbox_data, dict) else 60,
        default_max_tool_calls=int(sandbox_data.get("default_max_tool_calls", 20)) if isinstance(sandbox_data, dict) else 20,
        roles=[SandboxRoleConfig(**(r if isinstance(r, dict) else {})) for r in sandbox_roles],
    )
    compliance_data = merged.get("compliance") or {}
    compliance = ComplianceConfig(
        pii_redaction=bool(compliance_data.get("pii_redaction", True)) if isinstance(compliance_data, dict) else True,
        pii_types=compliance_data.get("pii_types", ["EMAIL", "PHONE", "SSN", "CREDIT_CARD", "API_KEY"]) if isinstance(compliance_data, dict) else ["EMAIL", "PHONE", "SSN", "CREDIT_CARD", "API_KEY"],
        gdpr_mode=bool(compliance_data.get("gdpr_mode", False)) if isinstance(compliance_data, dict) else False,
        audit_logging=bool(compliance_data.get("audit_logging", True)) if isinstance(compliance_data, dict) else True,
        data_residency=str(compliance_data.get("data_residency", "us")) if isinstance(compliance_data, dict) else "us",
    )
    hitl_data = merged.get("hitl") or {}
    hitl_policies = hitl_data.get("policies") if isinstance(hitl_data, dict) else []
    if not isinstance(hitl_policies, list):
        hitl_policies = []
    hitl_policy_configs = []
    for p in hitl_policies:
        if not isinstance(p, dict):
            continue
        triggers_data = p.get("triggers") or []
        triggers = [HitlTriggerConfig(**(t if isinstance(t, dict) else {})) for t in triggers_data if isinstance(t, dict)]
        hitl_policy_configs.append(
            HitlPolicyConfig(
                name=str(p.get("name", "")),
                on_timeout=str(p.get("on_timeout", "auto_approve")),
                timeout_seconds=int(p.get("timeout_seconds", 3600)),
                approvers=list(p.get("approvers") or []),
                triggers=triggers,
            )
        )
    hitl = HitlConfig(
        enabled=bool(hitl_data.get("enabled", False)) if isinstance(hitl_data, dict) else False,
        policies=hitl_policy_configs,
    )

    return devsperConfigModel(
        swarm=swarm,
        agents=agents,
        models=models,
        memory=memory,
        knowledge=knowledge,
        tools=tools,
        telemetry=telemetry,
        cache=cache,
        bus=bus,
        nodes=nodes,
        mcp=mcp,
        a2a=a2a,
        events_dir=merged.get("events_dir", ".devsper/events"),
        data_dir=merged.get("data_dir", ".devsper"),
        providers=providers,
        sandbox=sandbox,
        compliance=compliance,
        hitl=hitl,
    )
