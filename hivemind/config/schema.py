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


class ProviderOllamaConfig(BaseModel):
    """v2.0: Ollama local backend."""
    enabled: bool = False
    base_url: str = "http://localhost:11434"


class ProviderVLLMConfig(BaseModel):
    """v2.0: vLLM OpenAI-compatible endpoint."""
    enabled: bool = False
    base_url: str = "http://localhost:8000"
    api_key: str = ""


class ProviderCustomConfig(BaseModel):
    """v2.0: Custom OpenAI-compatible endpoint."""
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model_prefix_strip: str = ""


class ProvidersConfig(BaseModel):
    azure: ProviderAzureConfig = Field(default_factory=ProviderAzureConfig)
    ollama: ProviderOllamaConfig = Field(default_factory=ProviderOllamaConfig)
    vllm: ProviderVLLMConfig = Field(default_factory=ProviderVLLMConfig)
    custom: ProviderCustomConfig = Field(default_factory=ProviderCustomConfig)
    fallback_order: list[str] = Field(default_factory=lambda: [])


class SandboxRoleConfig(BaseModel):
    """v2.0: per-role sandbox overrides."""
    role: str = ""
    max_tool_calls: int | None = None
    allowed_tool_categories: list[str] | None = None
    blocked_tool_categories: list[str] = Field(default_factory=list)
    filesystem_write: bool = False


class SandboxConfig(BaseModel):
    """v2.0: agent sandbox resource quotas."""
    enabled: bool = True
    default_max_memory_mb: int = 512
    default_max_cpu_seconds: int = 60
    default_max_tool_calls: int = 20
    roles: list[SandboxRoleConfig] = Field(default_factory=list)


class ComplianceConfig(BaseModel):
    """v2.0: PII redaction and audit."""
    pii_redaction: bool = True
    pii_types: list[str] = Field(default_factory=lambda: ["EMAIL", "PHONE", "SSN", "CREDIT_CARD", "API_KEY"])
    gdpr_mode: bool = False
    audit_logging: bool = True
    data_residency: str = "us"


class NodesConfig(BaseModel):
    """v1.10: distributed node mode and RPC."""
    mode: Literal["single", "distributed"] = "single"
    role: Literal["controller", "worker", "hybrid"] = "hybrid"
    run_id: str | None = None  # shared run_id for distributed demo; None = generate (controller) or env (worker)
    rpc_port: int = 7700
    rpc_token: str | None = None
    max_workers_per_node: int = 8
    node_tags: list[str] = Field(default_factory=list)
    controller_url: str = "http://localhost:7700"
    heartbeat_interval_seconds: float = 10.0
    task_claim_timeout_seconds: int = 120
    deregister_stale_workers: bool = False  # if False, workers are never removed from registry (only in-memory stats cleared)
    claim_grant_wait_seconds: float = 15.0  # worker: max wait for TASK_CLAIM_GRANTED after claiming
    task_execution_timeout_seconds: int = 90  # worker: fail task if agent.run exceeds this (0 = no limit)


class MCPServerConfig(BaseModel):
    """v1.10.5: MCP server connection config."""
    name: str = ""
    transport: Literal["stdio", "http", "sse"] = "stdio"
    command: list[str] | None = None  # stdio: e.g. ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    url: str | None = None  # http/sse: e.g. "http://localhost:3000"
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    auto_reconnect: bool = True


class MCPConfig(BaseModel):
    """v1.10.5: MCP servers from [[mcp.servers]]."""
    servers: list[MCPServerConfig] = Field(default_factory=list)


class A2AAgentConfig(BaseModel):
    """v1.10.5: External A2A agent config."""
    name: str = ""
    url: str = ""
    auto_discover: bool = True  # fetch AgentCard on startup, register skills as tools


class A2AConfig(BaseModel):
    """v1.10.5: A2A agents and optional server exposure."""
    agents: list[A2AAgentConfig] = Field(default_factory=list)
    serve: bool = False  # expose this hivemind instance as A2A server
    serve_port: int = 8080


class HitlTriggerConfig(BaseModel):
    """v2.1: Single escalation trigger (e.g. cost_above, critic_score_below)."""
    type: str = "confidence_below"
    threshold: float | str = 0.5


class HitlPolicyConfig(BaseModel):
    """v2.1: HITL policy with triggers and approvers."""
    name: str = ""
    on_timeout: Literal["auto_approve", "auto_reject", "escalate_further"] = "auto_approve"
    timeout_seconds: int = 3600
    approvers: list[str] = Field(default_factory=list)
    triggers: list[HitlTriggerConfig] = Field(default_factory=list)


class HitlConfig(BaseModel):
    """v2.1: Human-in-the-loop escalation and approval."""
    enabled: bool = False
    policies: list[HitlPolicyConfig] = Field(default_factory=list)


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
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    a2a: A2AConfig = Field(default_factory=A2AConfig)
    events_dir: str = ".hivemind/events"
    data_dir: str = ".hivemind"
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    hitl: HitlConfig = Field(default_factory=HitlConfig)

    # Backward-compat aliases (property-style access from old HivemindConfig)
    @property
    def worker_model(self) -> str:
        return self.models.worker

    @property
    def planner_model(self) -> str:
        return self.models.planner
