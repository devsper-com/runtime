"""Tests for hivemind reg CLI commands.

Uses respx to mock HTTP requests and unittest.mock for token/credential helpers.
"""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

# We patch REGISTRY_URL at module level in the commands module
TEST_REGISTRY = "https://test-registry.example.com"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_registry_url(monkeypatch):
    """Point all registry calls at our test URL."""
    monkeypatch.setattr("hivemind.plugins.registry.REGISTRY_URL", TEST_REGISTRY)
    monkeypatch.setattr("hivemind.cli.commands.reg.REGISTRY_URL", TEST_REGISTRY)


@pytest.fixture()
def mock_token(monkeypatch):
    """Pretend user is logged in with a test token."""
    token = "hm_test_token_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    monkeypatch.setattr("hivemind.cli.commands.reg.get_token", lambda: token)
    monkeypatch.setattr("hivemind.cli.commands.reg.require_token", lambda: token)
    return token


@pytest.fixture()
def mock_no_token(monkeypatch):
    """Pretend user is NOT logged in."""
    monkeypatch.setattr("hivemind.cli.commands.reg.get_token", lambda: None)

    def _raise():
        raise SystemExit(1)

    monkeypatch.setattr("hivemind.cli.commands.reg.require_token", _raise)


@pytest.fixture()
def mock_set_token(monkeypatch):
    """Capture set_token calls."""
    calls = []
    monkeypatch.setattr(
        "hivemind.cli.commands.reg.set_token", lambda t: calls.append(t)
    )
    return calls


@pytest.fixture()
def mock_delete_token(monkeypatch):
    """Capture delete_token calls."""
    calls = []
    monkeypatch.setattr(
        "hivemind.cli.commands.reg.delete_token", lambda: calls.append(True)
    )
    return calls


def _make_args(**kwargs):
    """Build a namespace that looks like argparse output."""
    return argparse.Namespace(**kwargs)


# ── logout ─────────────────────────────────────────────────────────────────


class TestLogout:
    def test_logout_deletes_token(self, mock_delete_token):
        from hivemind.cli.commands.reg import cmd_logout

        rc = cmd_logout(_make_args())
        assert rc == 0
        assert mock_delete_token == [True]


# ── whoami ─────────────────────────────────────────────────────────────────


class TestWhoami:
    @respx.mock
    def test_whoami_success(self, mock_token):
        from hivemind.cli.commands.reg import cmd_whoami

        respx.get(f"{TEST_REGISTRY}/api/v1/me").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "abc-123",
                    "username": "testuser",
                    "email": "test@example.com",
                },
            )
        )
        rc = cmd_whoami(_make_args())
        assert rc == 0

    @respx.mock
    def test_whoami_401_exits(self, mock_token):
        from hivemind.cli.commands.reg import cmd_whoami

        respx.get(f"{TEST_REGISTRY}/api/v1/me").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        with pytest.raises(SystemExit):
            cmd_whoami(_make_args())

    def test_whoami_no_token(self, mock_no_token):
        from hivemind.cli.commands.reg import cmd_whoami

        with pytest.raises(SystemExit):
            cmd_whoami(_make_args())


# ── search ─────────────────────────────────────────────────────────────────


class TestSearch:
    @respx.mock
    def test_search_with_results(self):
        from hivemind.cli.commands.reg import cmd_search

        respx.get(f"{TEST_REGISTRY}/api/v1/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "packages": [
                        {
                            "name": "hivemind-plugin-demo",
                            "latest_version": "0.9.0",
                            "total_downloads": 42,
                            "verified": True,
                        },
                        {
                            "name": "hivemind-plugin-foo",
                            "latest_version": "1.0.0",
                            "total_downloads": 0,
                            "verified": False,
                        },
                    ]
                },
            )
        )
        rc = cmd_search(_make_args(query="hivemind", verified=False, limit=10))
        assert rc == 0

    @respx.mock
    def test_search_no_results(self):
        from hivemind.cli.commands.reg import cmd_search

        respx.get(f"{TEST_REGISTRY}/api/v1/search").mock(
            return_value=httpx.Response(200, json={"packages": []})
        )
        rc = cmd_search(_make_args(query="nonexistent", verified=False, limit=10))
        assert rc == 0

    @respx.mock
    def test_search_error(self):
        from hivemind.cli.commands.reg import cmd_search

        respx.get(f"{TEST_REGISTRY}/api/v1/search").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        rc = cmd_search(_make_args(query="test", verified=False, limit=10))
        # Should return 1 on error (raise_for_status triggers exception path)
        assert rc == 1


# ── info ───────────────────────────────────────────────────────────────────


class TestInfo:
    @respx.mock
    def test_info_success(self):
        from hivemind.cli.commands.reg import cmd_info

        respx.get(f"{TEST_REGISTRY}/api/v1/packages/hivemind-plugin-demo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "hivemind-plugin-demo",
                    "description": "A demo plugin",
                    "latest_version": "0.9.0",
                    "total_downloads": 42,
                    "verified": True,
                },
            )
        )
        rc = cmd_info(_make_args(package="hivemind-plugin-demo"))
        assert rc == 0

    @respx.mock
    def test_info_not_found(self):
        from hivemind.cli.commands.reg import cmd_info

        respx.get(f"{TEST_REGISTRY}/api/v1/packages/nope").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        with pytest.raises(SystemExit):
            cmd_info(_make_args(package="nope"))


# ── versions ───────────────────────────────────────────────────────────────


class TestVersions:
    @respx.mock
    def test_versions_success(self):
        from hivemind.cli.commands.reg import cmd_versions

        respx.get(
            f"{TEST_REGISTRY}/api/v1/packages/hivemind-plugin-demo/versions"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "versions": [
                        {
                            "version": "0.9.0",
                            "uploaded_at": "2025-03-12T10:00:00Z",
                            "download_count": 10,
                            "verification_status": "passed",
                            "yanked": False,
                        },
                        {
                            "version": "0.8.0",
                            "uploaded_at": "2025-03-11T10:00:00Z",
                            "download_count": 5,
                            "verification_status": "passed",
                            "yanked": False,
                        },
                    ]
                },
            )
        )
        rc = cmd_versions(_make_args(package="hivemind-plugin-demo"))
        assert rc == 0

    @respx.mock
    def test_versions_not_found(self):
        from hivemind.cli.commands.reg import cmd_versions

        respx.get(f"{TEST_REGISTRY}/api/v1/packages/nope/versions").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        with pytest.raises(SystemExit):
            cmd_versions(_make_args(package="nope"))

    @respx.mock
    def test_versions_empty(self):
        from hivemind.cli.commands.reg import cmd_versions

        respx.get(f"{TEST_REGISTRY}/api/v1/packages/demo/versions").mock(
            return_value=httpx.Response(200, json={"versions": []})
        )
        rc = cmd_versions(_make_args(package="demo"))
        assert rc == 0


# ── yank ───────────────────────────────────────────────────────────────────


class TestYank:
    @respx.mock
    def test_yank_success(self, mock_token):
        from hivemind.cli.commands.reg import cmd_yank

        respx.post(
            f"{TEST_REGISTRY}/api/v1/packages/hivemind-plugin-demo/0.1.0/yank"
        ).mock(return_value=httpx.Response(200, json={"ok": True}))
        rc = cmd_yank(
            _make_args(
                package="hivemind-plugin-demo",
                version="0.1.0",
                reason="security issue",
            )
        )
        assert rc == 0

    @respx.mock
    def test_yank_unauthorized(self, mock_token):
        from hivemind.cli.commands.reg import cmd_yank

        respx.post(
            f"{TEST_REGISTRY}/api/v1/packages/hivemind-plugin-demo/0.1.0/yank"
        ).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
        with pytest.raises(SystemExit):
            cmd_yank(
                _make_args(
                    package="hivemind-plugin-demo",
                    version="0.1.0",
                    reason="oops",
                )
            )

    def test_yank_no_token(self, mock_no_token):
        from hivemind.cli.commands.reg import cmd_yank

        with pytest.raises(SystemExit):
            cmd_yank(
                _make_args(
                    package="hivemind-plugin-demo",
                    version="0.1.0",
                    reason="no auth",
                )
            )


# ── test (validation) ─────────────────────────────────────────────────────


class TestTestCommand:
    def test_valid_plugin(self, tmp_path):
        """A minimal valid plugin passes all checks."""
        from hivemind.cli.commands.reg import cmd_test

        # Create pyproject.toml
        pyproject = {
            "project": {
                "name": "hivemind-test-plugin",
                "version": "0.1.0",
                "description": "Test plugin",
                "license": "MIT",
                "requires-python": ">=3.12",
                "entry-points": {"hivemind.plugins": {"test": "test_plugin:load"}},
            }
        }
        import tomllib

        # Write pyproject.toml manually (tomllib is read-only)
        pyproject_str = """
[project]
name = "hivemind-test-plugin"
version = "0.1.0"
description = "Test plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)

        # Create test_plugin.py with a load() that returns a list with a mock Tool
        (tmp_path / "test_plugin.py").write_text(
            """
class Tool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def run(self, **kwargs):
        return "ok"

def load():
    return [Tool("test-tool", "A test tool")]
"""
        )

        rc = cmd_test(_make_args(dir=str(tmp_path)))
        assert rc == 0

    def test_missing_pyproject(self, tmp_path):
        """No pyproject.toml -> SystemExit."""
        from hivemind.cli.commands.reg import cmd_test

        with pytest.raises(SystemExit):
            cmd_test(_make_args(dir=str(tmp_path)))

    def test_missing_version(self, tmp_path):
        """Missing version field fails."""
        from hivemind.cli.commands.reg import cmd_test

        pyproject_str = """
[project]
name = "hivemind-test-plugin"
description = "Test plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)
        (tmp_path / "test_plugin.py").write_text("def load():\n    return []\n")

        with pytest.raises(SystemExit):
            cmd_test(_make_args(dir=str(tmp_path)))


# ── publish (dry run) ─────────────────────────────────────────────────────


class TestPublish:
    def test_publish_dry_run(self, tmp_path, mock_token, monkeypatch):
        """Dry run prints files but doesn't upload."""
        from hivemind.cli.commands.reg import cmd_publish

        # Create a minimal valid plugin
        pyproject_str = """
[project]
name = "hivemind-test-plugin"
version = "0.1.0"
description = "Test plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)
        (tmp_path / "test_plugin.py").write_text(
            """
class Tool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def run(self, **kwargs):
        return "ok"

def load():
    return [Tool("test-tool", "A test tool")]
"""
        )

        # Pre-create dist with a fake wheel
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        fake_wheel = dist_dir / "hivemind_test_plugin-0.1.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"fake wheel content")

        rc = cmd_publish(_make_args(dir=str(tmp_path), skip_build=True, dry_run=True))
        assert rc == 0

    def test_publish_no_token(self, tmp_path, mock_no_token):
        """Publish without token exits."""
        from hivemind.cli.commands.reg import cmd_publish

        with pytest.raises(SystemExit):
            cmd_publish(_make_args(dir=str(tmp_path), skip_build=False, dry_run=False))

    @respx.mock
    def test_publish_upload_success(self, tmp_path, mock_token, monkeypatch):
        """Full publish flow: skip_build + existing dist -> upload succeeds."""
        from hivemind.cli.commands.reg import cmd_publish

        pyproject_str = """
[project]
name = "hivemind-test-plugin"
version = "0.2.0"
description = "Test plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)
        (tmp_path / "test_plugin.py").write_text(
            """
class Tool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def run(self, **kwargs):
        return "ok"

def load():
    return [Tool("test-tool", "A test tool")]
"""
        )
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        fake_wheel = dist_dir / "hivemind_test_plugin-0.2.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"fake wheel content")

        # Mock: package exists
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/hivemind-test-plugin").mock(
            return_value=httpx.Response(200, json={"name": "hivemind-test-plugin"})
        )

        # Mock: upload succeeds
        respx.post(f"{TEST_REGISTRY}/api/v1/packages/hivemind-test-plugin/upload").mock(
            return_value=httpx.Response(201, json={"ok": True})
        )

        # Mock: version status check (published)
        respx.get(
            f"{TEST_REGISTRY}/api/v1/packages/hivemind-test-plugin/versions/0.2.0/status"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "verification_status": "passed",
                    "tool_count": 1,
                },
            )
        )

        rc = cmd_publish(_make_args(dir=str(tmp_path), skip_build=True, dry_run=False))
        assert rc == 0

    @respx.mock
    def test_publish_creates_package_if_not_found(
        self, tmp_path, mock_token, monkeypatch
    ):
        """If package doesn't exist, auto-creates it."""
        from hivemind.cli.commands.reg import cmd_publish

        pyproject_str = """
[project]
name = "hivemind-new-plugin"
version = "0.1.0"
description = "Brand new plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)
        (tmp_path / "test_plugin.py").write_text(
            """
class Tool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def run(self, **kwargs):
        return "ok"

def load():
    return [Tool("test-tool", "A test tool")]
"""
        )
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        fake_wheel = dist_dir / "hivemind_new_plugin-0.1.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"fake wheel content")

        # Package doesn't exist
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/hivemind-new-plugin").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        # Create succeeds
        respx.post(f"{TEST_REGISTRY}/api/v1/packages").mock(
            return_value=httpx.Response(201, json={"name": "hivemind-new-plugin"})
        )
        # Upload succeeds
        respx.post(f"{TEST_REGISTRY}/api/v1/packages/hivemind-new-plugin/upload").mock(
            return_value=httpx.Response(201, json={"ok": True})
        )
        # Version check
        respx.get(
            f"{TEST_REGISTRY}/api/v1/packages/hivemind-new-plugin/versions/0.1.0/status"
        ).mock(
            return_value=httpx.Response(
                200, json={"verification_status": "passed", "tool_count": 1}
            )
        )

        rc = cmd_publish(_make_args(dir=str(tmp_path), skip_build=True, dry_run=False))
        assert rc == 0

    @respx.mock
    def test_publish_version_conflict(self, tmp_path, mock_token, monkeypatch):
        """Upload returns 409 -> version already exists."""
        from hivemind.cli.commands.reg import cmd_publish

        pyproject_str = """
[project]
name = "hivemind-test-plugin"
version = "0.1.0"
description = "Test plugin"
license = "MIT"
requires-python = ">=3.12"

[project.entry-points."hivemind.plugins"]
test = "test_plugin:load"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_str)
        (tmp_path / "test_plugin.py").write_text(
            """
class Tool:
    def __init__(self, name, description):
        self.name = name
        self.description = description
    def run(self, **kwargs):
        return "ok"

def load():
    return [Tool("test-tool", "A test tool")]
"""
        )
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        fake_wheel = dist_dir / "hivemind_test_plugin-0.1.0-py3-none-any.whl"
        fake_wheel.write_bytes(b"fake wheel content")

        # Package exists
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/hivemind-test-plugin").mock(
            return_value=httpx.Response(200, json={"name": "hivemind-test-plugin"})
        )
        # Upload returns conflict
        respx.post(f"{TEST_REGISTRY}/api/v1/packages/hivemind-test-plugin/upload").mock(
            return_value=httpx.Response(409, text="version already exists")
        )

        with pytest.raises(SystemExit):
            cmd_publish(_make_args(dir=str(tmp_path), skip_build=True, dry_run=False))


# ── login ──────────────────────────────────────────────────────────────────


class TestLogin:
    @respx.mock
    def test_login_immediate_approval(self, mock_set_token, monkeypatch):
        """Device flow: request + immediate approval on first poll."""
        from hivemind.cli.commands.reg import cmd_login

        # Mock device request
        respx.post(f"{TEST_REGISTRY}/api/v1/auth/device/request").mock(
            return_value=httpx.Response(
                200,
                json={
                    "device_code": "dc-123",
                    "user_code": "ABCD-1234",
                    "verification_uri": f"{TEST_REGISTRY}/activate",
                    "expires_in": 10,
                    "interval": 0,  # poll immediately
                },
            )
        )
        # Mock poll: immediately returns token
        respx.post(f"{TEST_REGISTRY}/api/v1/auth/device/poll").mock(
            return_value=httpx.Response(
                200,
                json={"token": "hm_new_token_from_device_flow"},
            )
        )

        # Patch time.sleep to avoid waiting, and Live to avoid Rich rendering issues
        monkeypatch.setattr("hivemind.cli.commands.reg.time.sleep", lambda s: None)

        rc = cmd_login(_make_args())
        assert rc == 0
        assert mock_set_token == ["hm_new_token_from_device_flow"]

    @respx.mock
    def test_login_denied(self, monkeypatch):
        """Device flow: request + poll returns 400 (denied)."""
        from hivemind.cli.commands.reg import cmd_login

        respx.post(f"{TEST_REGISTRY}/api/v1/auth/device/request").mock(
            return_value=httpx.Response(
                200,
                json={
                    "device_code": "dc-456",
                    "user_code": "EFGH-5678",
                    "verification_uri": f"{TEST_REGISTRY}/activate",
                    "expires_in": 10,
                    "interval": 0,
                },
            )
        )
        respx.post(f"{TEST_REGISTRY}/api/v1/auth/device/poll").mock(
            return_value=httpx.Response(400, json={"error": "denied"})
        )
        monkeypatch.setattr("hivemind.cli.commands.reg.time.sleep", lambda s: None)

        with pytest.raises(SystemExit):
            cmd_login(_make_args())

    @respx.mock
    def test_login_registry_unreachable(self):
        """Device flow: cannot reach registry at all."""
        from hivemind.cli.commands.reg import cmd_login

        respx.post(f"{TEST_REGISTRY}/api/v1/auth/device/request").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(SystemExit):
            cmd_login(_make_args())


# ── _ensure_package_exists ─────────────────────────────────────────────────


class TestEnsurePackageExists:
    @respx.mock
    def test_package_already_exists(self, mock_token):
        from hivemind.cli.commands.reg import _ensure_package_exists, RegistryClient

        client = RegistryClient(mock_token)
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/my-pkg").mock(
            return_value=httpx.Response(200, json={"name": "my-pkg"})
        )
        # Should not raise
        _ensure_package_exists(client, "my-pkg", {})

    @respx.mock
    def test_package_created(self, mock_token):
        from hivemind.cli.commands.reg import _ensure_package_exists, RegistryClient

        client = RegistryClient(mock_token)
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/new-pkg").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        respx.post(f"{TEST_REGISTRY}/api/v1/packages").mock(
            return_value=httpx.Response(201, json={"name": "new-pkg"})
        )
        _ensure_package_exists(
            client,
            "new-pkg",
            {"project": {"name": "new-pkg", "description": "A new package"}},
        )

    @respx.mock
    def test_package_creation_fails(self, mock_token):
        from hivemind.cli.commands.reg import _ensure_package_exists, RegistryClient

        client = RegistryClient(mock_token)
        respx.get(f"{TEST_REGISTRY}/api/v1/packages/fail-pkg").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        respx.post(f"{TEST_REGISTRY}/api/v1/packages").mock(
            return_value=httpx.Response(500, text="internal error")
        )
        with pytest.raises(SystemExit):
            _ensure_package_exists(client, "fail-pkg", {})


# ── _read_pyproject ────────────────────────────────────────────────────────


class TestReadPyproject:
    def test_read_existing(self, tmp_path):
        from hivemind.cli.commands.reg import _read_pyproject

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\nversion = "1.0.0"\n'
        )
        result = _read_pyproject(tmp_path)
        assert result["project"]["name"] == "test"
        assert result["project"]["version"] == "1.0.0"

    def test_read_missing(self, tmp_path):
        from hivemind.cli.commands.reg import _read_pyproject

        result = _read_pyproject(tmp_path)
        assert result == {}


# ── RegistryClient ─────────────────────────────────────────────────────────


class TestRegistryClient:
    def test_client_default_no_token(self):
        from hivemind.plugins.registry import RegistryClient

        client = RegistryClient()
        assert client.base == TEST_REGISTRY
        assert client.token is None
        headers = client._headers()
        assert "X-API-Key" not in headers
        client.close()

    def test_client_with_token(self):
        from hivemind.plugins.registry import RegistryClient

        client = RegistryClient("my-token")
        assert client.token == "my-token"
        headers = client._headers()
        assert headers["X-API-Key"] == "my-token"
        client.close()

    @respx.mock
    def test_client_get(self):
        from hivemind.plugins.registry import RegistryClient

        respx.get(f"{TEST_REGISTRY}/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        client = RegistryClient()
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        client.close()

    @respx.mock
    def test_client_post(self):
        from hivemind.plugins.registry import RegistryClient

        respx.post(f"{TEST_REGISTRY}/api/v1/test").mock(
            return_value=httpx.Response(201, json={"created": True})
        )
        client = RegistryClient("tok")
        r = client.post("/api/v1/test", json={"key": "val"})
        assert r.status_code == 201
        client.close()
