"""Provider definitions for credential management."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Field:
    """A single credential field for a provider."""

    name: str
    display_name: str
    env_var: str
    secret: bool = True
    optional: bool = False
    default: str | None = None


@dataclass
class Provider:
    """A credential provider definition."""

    name: str
    display_name: str
    fields: list[Field] = field(default_factory=list)


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        name="anthropic",
        display_name="Anthropic",
        fields=[Field("api_key", "API Key", env_var="ANTHROPIC_API_KEY", secret=True)],
    ),
    "openai": Provider(
        name="openai",
        display_name="OpenAI",
        fields=[Field("api_key", "API Key", env_var="OPENAI_API_KEY", secret=True)],
    ),
    "github": Provider(
        name="github",
        display_name="GitHub Models",
        fields=[Field("token", "Token", env_var="GITHUB_TOKEN", secret=True)],
    ),
    "zai": Provider(
        name="zai",
        display_name="ZAI (z.ai)",
        fields=[
            Field("api_key", "API Key", env_var="ZAI_API_KEY", secret=True),
            Field(
                "base_url",
                "Base URL",
                env_var="ZAI_BASE_URL",
                secret=False,
                optional=True,
                default="https://api.z.ai/v1",
            ),
        ],
    ),
    "azure-openai": Provider(
        name="azure-openai",
        display_name="Azure OpenAI",
        fields=[
            Field("api_key", "API Key", env_var="AZURE_OPENAI_API_KEY", secret=True),
            Field("endpoint", "Endpoint", env_var="AZURE_OPENAI_ENDPOINT", secret=False),
            Field("deployment", "Deployment Name", env_var="AZURE_OPENAI_DEPLOYMENT", secret=False),
            Field(
                "api_version",
                "API Version",
                env_var="AZURE_OPENAI_API_VERSION",
                secret=False,
                optional=True,
                default="2024-02-01",
            ),
        ],
    ),
    "azure-foundry": Provider(
        name="azure-foundry",
        display_name="Azure AI Foundry (Anthropic)",
        fields=[
            Field("api_key", "API Key", env_var="AZURE_FOUNDRY_API_KEY", secret=True),
            Field("endpoint", "Endpoint", env_var="AZURE_FOUNDRY_ENDPOINT", secret=False),
            Field("deployment", "Deployment Name", env_var="AZURE_FOUNDRY_DEPLOYMENT", secret=False),
        ],
    ),
    "litellm": Provider(
        name="litellm",
        display_name="LiteLLM Proxy",
        fields=[
            Field("base_url", "Base URL", env_var="LITELLM_BASE_URL", secret=False),
            Field("api_key", "API Key", env_var="LITELLM_API_KEY", secret=True, optional=True),
        ],
    ),
    "ollama": Provider(
        name="ollama",
        display_name="Ollama",
        fields=[
            Field(
                "base_url",
                "Base URL",
                env_var="OLLAMA_HOST",
                secret=False,
                optional=True,
                default="http://localhost:11434",
            ),
        ],
    ),
}
