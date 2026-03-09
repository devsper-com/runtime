"""Tests for repo scaffolding (hivemind.dev.scaffold)."""

import tempfile
from pathlib import Path

import pytest

from hivemind.dev.scaffold import ArchitecturePlan, scaffold_repo


def test_scaffold_repo_creates_structure():
    with tempfile.TemporaryDirectory() as tmp:
        plan = ArchitecturePlan(
            name="TestApp",
            description="A test app",
            backend="fastapi",
            frontend="none",
        )
        created = scaffold_repo(tmp, plan)
        assert "backend/" in created
        assert "frontend/" in created
        assert "tests/" in created
        assert "docker/" in created
        assert "README.md" in created
        assert (Path(tmp) / "README.md").is_file()
        assert (Path(tmp) / "backend" / "main.py").is_file()
        assert (Path(tmp) / "backend" / "requirements.txt").is_file()
        assert (Path(tmp) / "tests" / "test_app.py").is_file()
        assert (Path(tmp) / "docker" / "Dockerfile").is_file()


def test_scaffold_fastapi_has_fastapi_content():
    with tempfile.TemporaryDirectory() as tmp:
        plan = ArchitecturePlan(
            name="API",
            description="API",
            backend="fastapi",
            frontend="none",
        )
        scaffold_repo(tmp, plan)
        main = (Path(tmp) / "backend" / "main.py").read_text()
        assert "FastAPI" in main
        assert "uvicorn" in (Path(tmp) / "backend" / "requirements.txt").read_text()


def test_scaffold_flask_has_flask_content():
    with tempfile.TemporaryDirectory() as tmp:
        plan = ArchitecturePlan(
            name="Web",
            description="Web",
            backend="flask",
            frontend="none",
        )
        scaffold_repo(tmp, plan)
        main = (Path(tmp) / "backend" / "main.py").read_text()
        assert "Flask" in main
