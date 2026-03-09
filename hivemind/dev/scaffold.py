"""
Repo scaffolder: generate repo structure from an architecture plan.

Structure: repo/backend/, frontend/, tests/, docker/, README.md
"""

from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ArchitecturePlan:
    """High-level architecture for the app to build."""

    name: str
    description: str
    backend: str  # e.g. "fastapi", "flask"
    frontend: str  # e.g. "react", "vanilla", "none"
    features: list[str] = field(default_factory=list)


def scaffold_repo(
    root: str | Path,
    plan: ArchitecturePlan,
) -> list[str]:
    """
    Create directory structure and minimal files based on architecture plan.
    Returns list of created paths (relative to root).
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    # Directories
    dirs = ["backend", "frontend", "tests", "docker"]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)
        created.append(d + "/")

    # README
    readme = f"""# {plan.name}

{plan.description}

## Structure

- `backend/` — {plan.backend} API
- `frontend/` — {plan.frontend} UI
- `tests/` — integration and unit tests
- `docker/` — container config

## Run

### Backend
```bash
cd backend && pip install -r requirements.txt && python -m uvicorn main:app --reload
```

### Frontend (if applicable)
```bash
cd frontend && npm install && npm run dev
```
"""
    (root / "README.md").write_text(readme, encoding="utf-8")
    created.append("README.md")

    # Backend scaffold based on plan.backend
    backend_dir = root / "backend"
    if "fastapi" in plan.backend.lower():
        (backend_dir / "main.py").write_text(
            '"""FastAPI app entrypoint."""\n\nfrom fastapi import FastAPI\n\napp = FastAPI(title="'
            + plan.name.replace('"', "'")
            + '")\n\n\n@app.get("/")\ndef root():\n    return {"message": "Hello"}\n',
            encoding="utf-8",
        )
        created.append("backend/main.py")
        (backend_dir / "requirements.txt").write_text(
            "fastapi>=0.100.0\nuvicorn[standard]>=0.22.0\n",
            encoding="utf-8",
        )
        created.append("backend/requirements.txt")
    elif "flask" in plan.backend.lower():
        (backend_dir / "main.py").write_text(
            '"""Flask app entrypoint."""\n\nfrom flask import Flask\n\napp = Flask(__name__)\n\n\n@app.route("/")\ndef root():\n    return {"message": "Hello"}\n',
            encoding="utf-8",
        )
        created.append("backend/main.py")
        (backend_dir / "requirements.txt").write_text(
            "flask>=3.0.0\n",
            encoding="utf-8",
        )
        created.append("backend/requirements.txt")
    else:
        (backend_dir / "main.py").write_text(
            '"""App entrypoint."""\n\n# TODO: implement\n',
            encoding="utf-8",
        )
        (backend_dir / "requirements.txt").write_text(
            "\n",
            encoding="utf-8",
        )
        created.append("backend/main.py")
        created.append("backend/requirements.txt")

    # Tests
    tests_dir = root / "tests"
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_app.py").write_text(
        '"""Basic tests."""\nimport pytest\n\n\ndef test_placeholder():\n    assert True\n',
        encoding="utf-8",
    )
    created.append("tests/__init__.py")
    created.append("tests/test_app.py")

    # Docker placeholder
    (root / "docker" / "Dockerfile").write_text(
        "# Dockerfile placeholder\nFROM python:3.12-slim\nWORKDIR /app\nCOPY backend/ .\nRUN pip install -r requirements.txt\nCMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\"]\n",
        encoding="utf-8",
    )
    created.append("docker/Dockerfile")

    return created
