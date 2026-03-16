"""
Autonomous Application Builder: build working repos from app descriptions.

Modules:
- builder: orchestrates architecture → scaffold → implement → test → debug
- scaffold: repo structure generation (backend, frontend, tests, docker)
- sandbox: isolated execution with timeout and resource limits
- debugger: test run → error detection → fix tasks → patch loop
- repo_index: AST parsing, dependency graph, symbol search (code intelligence)
- agents: dev-specific roles (architect, backend, frontend, test, review)
"""

from devsper.dev.builder import run_build
from devsper.dev.scaffold import scaffold_repo
from devsper.dev.sandbox import Sandbox
from devsper.dev.debugger import debug_loop
from devsper.dev.repo_index import RepoIndex

__all__ = [
    "run_build",
    "scaffold_repo",
    "Sandbox",
    "debug_loop",
    "RepoIndex",
]
