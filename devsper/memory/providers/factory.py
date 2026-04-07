"""
MemoryProviderFactory — analogous to providers/router/factory.py.

get_memory_provider() returns a process-level singleton MemoryBackend.

Provider resolution precedence:
  1. config.memory.provider (new explicit field in [memory] TOML section)
  2. DEVSPER_MEMORY_PROVIDER environment variable
  3. Legacy backend mapping: local/supermemory/hybrid → "vektori", platform → "platform"
  4. Default: "vektori"

Graceful fallback:
  If the resolved provider is "vektori" but DATABASE_URL is not set,
  emits a warning and falls back to "sqlite" so local dev without Postgres works.
"""

from __future__ import annotations

import logging
import os
import warnings

from devsper.memory.providers.base import MemoryBackend

log = logging.getLogger(__name__)

_provider_instance: MemoryBackend | None = None

# Legacy backend string → new provider name
_LEGACY_BACKEND_MAP: dict[str, str] = {
    "local": "vektori",
    "supermemory": "vektori",
    "hybrid": "vektori",
    "platform": "platform",
}


def _resolve_provider_name(cfg) -> str:
    """Determine which provider to instantiate from config + env."""
    # 1. Explicit new field
    provider = getattr(cfg, "provider", "") or ""
    if provider.strip():
        return provider.strip().lower()

    # 2. Environment variable override
    env = os.environ.get("DEVSPER_MEMORY_PROVIDER", "").strip().lower()
    if env:
        return env

    # 3. Legacy backend mapping
    legacy = getattr(cfg, "backend", "supermemory") or "supermemory"
    if legacy in _LEGACY_BACKEND_MAP:
        return _LEGACY_BACKEND_MAP[legacy]

    # 4. Default
    return "vektori"


def _make_vektori_or_fallback() -> MemoryBackend:
    """Return VektoriBackend if DATABASE_URL is set, else SQLite with a warning."""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        from devsper.memory.providers.backends.vektori_backend import VektoriBackend

        return VektoriBackend()

    warnings.warn(
        "Memory provider 'vektori' selected but DATABASE_URL is not set. "
        "Falling back to SQLite. Set DATABASE_URL to use Postgres/pgvector memory.",
        UserWarning,
        stacklevel=3,
    )
    from devsper.memory.providers.backends.sqlite_backend import SQLiteBackend

    return SQLiteBackend()


def get_memory_provider(config=None) -> MemoryBackend:
    """
    Build and return the process-level MemoryBackend singleton.

    Args:
        config: Optional MemoryConfig instance. If None, loads from get_config().

    Returns:
        A MemoryBackend ready for use.
    """
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    if config is None:
        try:
            from devsper.config import get_config

            config = get_config().memory
        except Exception:
            config = None

    provider_name = _resolve_provider_name(config) if config is not None else "vektori"

    backend: MemoryBackend

    if provider_name == "vektori":
        backend = _make_vektori_or_fallback()

    elif provider_name == "sqlite":
        from devsper.memory.providers.backends.sqlite_backend import SQLiteBackend

        backend = SQLiteBackend()

    elif provider_name == "redis":
        redis_cfg = getattr(config, "redis", None) if config is not None else None
        redis_url = (
            os.environ.get("REDIS_URL", "")
            or getattr(redis_cfg, "redis_url", "redis://localhost:6379")
        )
        run_id = (
            getattr(redis_cfg, "run_id", "") or os.environ.get("DEVSPER_RUN_ID", "") or str(os.getpid())
        )
        from devsper.memory.providers.backends.redis_backend import RedisBackend

        backend = RedisBackend(redis_url=redis_url, run_id=run_id)

    elif provider_name == "snowflake":
        sf_cfg = getattr(config, "snowflake", None) if config is not None else None
        from devsper.memory.providers.backends.snowflake_backend import SnowflakeBackend

        backend = SnowflakeBackend(
            account=getattr(sf_cfg, "account", "") if sf_cfg else "",
            user=getattr(sf_cfg, "user", "") if sf_cfg else "",
            database=getattr(sf_cfg, "database", "") if sf_cfg else "",
            schema=getattr(sf_cfg, "schema_name", "") if sf_cfg else "",
            warehouse=getattr(sf_cfg, "warehouse", "") if sf_cfg else "",
            role=getattr(sf_cfg, "role", "") if sf_cfg else "",
            table=getattr(sf_cfg, "table", "devsper_memory") if sf_cfg else "devsper_memory",
        )

    elif provider_name == "platform":
        base_url = getattr(config, "platform_api_url", "") if config is not None else ""
        org_slug = getattr(config, "platform_org_slug", "") if config is not None else ""
        from devsper.memory.providers.backends.platform_backend import PlatformBackend

        backend = PlatformBackend(base_url=base_url, org_slug=org_slug)

    else:
        warnings.warn(
            f"Unknown memory provider '{provider_name}', falling back to vektori/sqlite.",
            UserWarning,
            stacklevel=2,
        )
        backend = _make_vektori_or_fallback()

    log.info("memory_provider_initialized provider=%s", backend.name)
    _provider_instance = backend
    return _provider_instance


def reset_memory_provider() -> None:
    """Reset the singleton. Used in tests and for hot-reload scenarios."""
    global _provider_instance
    _provider_instance = None
