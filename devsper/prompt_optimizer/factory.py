"""
Singleton factory for the active PromptOptimizerBackend.

Resolution order:
  1. DEVSPER_PROMPT_OPTIMIZER env var
  2. config.prompt_optimizer.provider (devsper.toml)
  3. Auto-detect: "dspy" if dspy-ai is importable, else "gepa"
     (GEPABackend ships a built-in evolutionary loop — no extra install needed)

Set provider = "noop" explicitly to disable optimization.
"""

from __future__ import annotations

import logging
import os

from devsper.prompt_optimizer.base import PromptOptimizerBackend

logger = logging.getLogger(__name__)

_optimizer_instance: PromptOptimizerBackend | None = None


def get_prompt_optimizer(config=None) -> PromptOptimizerBackend:
    """Return the active (singleton) PromptOptimizerBackend."""
    global _optimizer_instance
    if _optimizer_instance is not None:
        return _optimizer_instance

    _optimizer_instance = _build_optimizer(config)
    return _optimizer_instance


def reset_prompt_optimizer() -> None:
    """Clear the singleton (useful in tests)."""
    global _optimizer_instance
    _optimizer_instance = None


def _build_optimizer(config=None) -> PromptOptimizerBackend:
    provider_name = _resolve_provider_name(config)
    logger.debug("[prompt_optimizer] Using backend: %s", provider_name)

    if provider_name == "dspy":
        from devsper.prompt_optimizer.backends.dspy_backend import DSPyBackend

        cfg = _opt_cfg(config)
        return DSPyBackend(
            optimizer=getattr(cfg, "dspy_optimizer", "bootstrap"),
            max_bootstrapped_demos=getattr(cfg, "max_demos", 4),
            num_candidates=getattr(cfg, "num_candidates", 10),
        )

    if provider_name == "gepa":
        from devsper.prompt_optimizer.backends.gepa_backend import GEPABackend

        cfg = _opt_cfg(config)
        return GEPABackend(
            population_size=getattr(cfg, "population_size", 5),
        )

    # Default / noop
    from devsper.prompt_optimizer.backends.noop import NoopBackend
    return NoopBackend()


def _resolve_provider_name(config=None) -> str:
    # 1. Environment variable
    env = os.environ.get("DEVSPER_PROMPT_OPTIMIZER", "").strip().lower()
    if env:
        return env

    # 2. Config field
    cfg = _opt_cfg(config)
    if cfg:
        provider = getattr(cfg, "provider", "").strip().lower()
        if provider:
            return provider

    # 3. Auto-detect: prefer dspy if importable, otherwise gepa
    return _autodetect()


def _autodetect() -> str:
    """Return 'dspy' if dspy-ai is installed, else 'gepa' (always available)."""
    try:
        import dspy  # noqa: F401
        return "dspy"
    except ImportError:
        return "gepa"


def _opt_cfg(config=None):
    """Return the prompt_optimizer config section, or None."""
    if config is not None:
        return getattr(config, "prompt_optimizer", None)
    try:
        from devsper.config.config_loader import get_config
        return get_config().prompt_optimizer
    except Exception:
        return None
