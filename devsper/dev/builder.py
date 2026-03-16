"""
Autonomous Application Builder: build a working repo from an app description.

Flow:
1) architecture design
2) repo scaffold
3) module implementation
4) test generation
5) test execution
6) debugging loop
"""

from pathlib import Path

from devsper.dev.scaffold import ArchitecturePlan, scaffold_repo
from devsper.dev.sandbox import Sandbox, SandboxLimits
from devsper.dev.debugger import debug_loop
from devsper.dev.repo_index import RepoIndex


def _design_architecture(description: str) -> ArchitecturePlan:
    """Produce an architecture plan from app description (heuristic + optional LLM)."""
    desc_lower = (description or "").lower()
    name = (description or "app").strip()[:50].replace("/", "-")
    backend = "fastapi"
    frontend = "none"
    if "flask" in desc_lower:
        backend = "flask"
    if "react" in desc_lower or "frontend" in desc_lower or "ui" in desc_lower:
        frontend = "react"
    if "todo" in desc_lower:
        name = "Todo App"
    return ArchitecturePlan(
        name=name or "App",
        description=description or "Generated application",
        backend=backend,
        frontend=frontend,
        features=[],
    )


def _implement_modules(sandbox: Sandbox, plan: ArchitecturePlan, description: str) -> None:
    """Generate and write main backend module(s)."""
    if "fastapi" in plan.backend.lower() and "todo" in plan.name.lower():
        main_py = '''"""FastAPI Todo API."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Todo API")

class TodoItem(BaseModel):
    id: int
    title: str
    done: bool = False

todos: List[TodoItem] = []
next_id = 1

@app.get("/")
def root():
    return {"message": "Todo API", "docs": "/docs"}

@app.get("/todos")
def list_todos():
    return {"todos": [t.model_dump() for t in todos]}

@app.post("/todos")
def create_todo(title: str):
    global next_id
    item = TodoItem(id=next_id, title=title, done=False)
    next_id += 1
    todos.append(item)
    return item.model_dump()

@app.patch("/todos/{item_id}")
def toggle_todo(item_id: int):
    for t in todos:
        if t.id == item_id:
            t.done = not t.done
            return t.model_dump()
    raise HTTPException(status_code=404, detail="Not found")

@app.delete("/todos/{item_id}")
def delete_todo(item_id: int):
    global todos
    for i, t in enumerate(todos):
        if t.id == item_id:
            todos.pop(i)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Not found")
'''
        sandbox.write_file("backend/main.py", main_py)
    elif "fastapi" in plan.backend.lower():
        # Generic FastAPI placeholder already from scaffold; leave or minimal enhance
        pass


def _generate_tests(sandbox: Sandbox, plan: ArchitecturePlan) -> None:
    """Write basic tests."""
    if "todo" in (plan.name or "").lower():
        test_py = '''"""Tests for Todo API."""
import pytest
from fastapi.testclient import TestClient

# Import app from backend
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from main import app

client = TestClient(app)

def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "message" in r.json()

def test_list_todos_empty():
    r = client.get("/todos")
    assert r.status_code == 200
    assert r.json()["todos"] == []

def test_create_and_list_todo():
    r = client.post("/todos?title=test task")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "test task"
    assert data["done"] is False
    r2 = client.get("/todos")
    assert len(r2.json()["todos"]) >= 1
'''
        sandbox.write_file("tests/test_app.py", test_py)


def run_build(
    app_description: str,
    output_dir: str | Path,
    *,
    timeout_seconds: int = 300,
    max_debug_iterations: int = 3,
) -> dict:
    """
    Build a working repository from an app description.

    Steps: architecture design, scaffold, implement, generate tests,
    install deps, run tests, debug loop until pass or limit.

    Returns dict with keys: success, plan, created_paths, test_passed, debug_result, repo_path.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    plan = _design_architecture(app_description)
    created_paths = scaffold_repo(output_dir, plan)

    limits = SandboxLimits(timeout_seconds=timeout_seconds)
    sandbox = Sandbox(output_dir, limits=limits)

    _implement_modules(sandbox, plan, app_description)
    _generate_tests(sandbox, plan)

    install_result = sandbox.install_dependencies(backend=True, frontend=False)

    def get_fix(stdout: str, stderr: str) -> str:
        try:
            from devsper.utils.models import generate
            from devsper.config import get_config
            cfg = get_config()
            model = getattr(cfg.swarm, "worker_model", "gpt-4o") or "gpt-4o"
            prompt = (
                "The following test run failed. Suggest a single file fix as:\n"
                "FILE: <relative path>\nCONTENT: <full file content>\n\n"
                "Stdout:\n" + (stdout or "")[:2000] + "\n\nStderr:\n" + (stderr or "")[:1000]
            )
            return generate(model, prompt)
        except Exception:
            return ""

    debug_result = debug_loop(
        sandbox,
        max_iterations=max_debug_iterations,
        test_path="tests",
        get_fix=get_fix,
    )

    return {
        "success": debug_result.passed,
        "plan": plan,
        "created_paths": created_paths,
        "install_success": install_result.success,
        "test_passed": debug_result.passed,
        "debug_result": debug_result,
        "repo_path": str(output_dir),
    }
