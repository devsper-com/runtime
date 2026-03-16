"""Tests for config loader, schema, resolver."""

from devsper.config import get_config
from devsper.config.config_loader import normalize_toml_to_flat
from devsper.config.schema import devsperConfigModel, SwarmConfig, ToolsConfig


def test_get_config_returns_model():
    cfg = get_config()
    assert isinstance(cfg, devsperConfigModel)
    assert hasattr(cfg, "worker_model")
    assert hasattr(cfg, "planner_model")
    assert hasattr(cfg, "events_dir")
    assert hasattr(cfg, "data_dir")
    assert hasattr(cfg, "swarm")
    assert hasattr(cfg, "tools")


def test_config_has_swarm_and_tools():
    cfg = get_config()
    assert isinstance(cfg.swarm, SwarmConfig)
    assert isinstance(cfg.tools, ToolsConfig)
    assert cfg.swarm.workers >= 1
    assert cfg.swarm.max_iterations >= 1


def test_env_override_worker_model(monkeypatch):
    monkeypatch.setenv("DEVSPER_WORKER_MODEL", "test-worker")
    cfg = get_config()
    assert cfg.worker_model == "test-worker"
    monkeypatch.delenv("DEVSPER_WORKER_MODEL", raising=False)


def test_normalize_toml_legacy():
    data = {"default": {"worker_model": "gpt-4o", "events_dir": "/tmp/ev"}}
    out = normalize_toml_to_flat(data)
    assert out.get("worker_model") == "gpt-4o"
    assert out.get("events_dir") == "/tmp/ev"


def test_normalize_toml_new_format():
    data = {
        "swarm": {"workers": 8, "adaptive_planning": True},
        "models": {"planner": "azure:gpt-4o", "worker": "azure:gpt-4o"},
    }
    out = normalize_toml_to_flat(data)
    assert out.get("swarm") == {"workers": 8, "adaptive_planning": True}
    assert out.get("models", {}).get("planner") == "azure:gpt-4o"
