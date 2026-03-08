"""Tests for GitHub Models provider."""

import os
from unittest.mock import patch

import pytest

from hivemind.providers.github import GitHubProvider
from hivemind.providers.router import ProviderRouter, _parse_model_spec


def test_parse_model_spec_github():
    """provider:model format parses to (vendor, model_name)."""
    assert _parse_model_spec("github:gpt-4o") == ("github", "gpt-4o")
    assert _parse_model_spec("github:claude-3.5-sonnet") == ("github", "claude-3.5-sonnet")
    assert _parse_model_spec("github:phi-3") == ("github", "phi-3")


def test_github_provider_requires_token():
    """GitHubProvider raises when GITHUB_TOKEN is not set."""
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubProvider()
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubProvider(token="")


def test_github_provider_strips_prefix_in_generate():
    """When model is 'github:gpt-4o', API receives 'gpt-4o'."""
    token = "test-token"
    with patch("hivemind.providers.github.httpx.Client") as mock_client:
        mock_post = mock_client.return_value.__enter__.return_value.post
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"choices": [{"message": {"content": "Hi"}}]}
        provider = GitHubProvider(token=token)
        out = provider.generate("github:gpt-4o", "Hello", stream=False)
        assert out == "Hi"
        call_kw = mock_post.call_args
        assert call_kw[1]["json"]["model"] == "gpt-4o"


def test_router_returns_github_provider_for_github_spec():
    """get_provider('github:gpt-4o') returns GitHubProvider when token set."""
    with patch.dict(os.environ, {"GITHUB_TOKEN": "x"}, clear=False):
        router = ProviderRouter()
        provider = router.get_provider("github:gpt-4o")
        assert isinstance(provider, GitHubProvider)
