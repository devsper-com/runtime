"""
Code sandbox: write files, run shell commands, run tests, install dependencies.

Enforces timeout and resource limits for safe autonomous execution.
"""

import os
import subprocess
import sys
import shlex
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None  # Windows has no resource module
from dataclasses import dataclass, field


@dataclass
class SandboxResult:
    """Result of a sandboxed command or operation."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False
    error: str | None = None


@dataclass
class SandboxLimits:
    """Resource limits for sandbox execution."""

    timeout_seconds: int = 300
    max_memory_mb: int | None = 100
    max_cpu_seconds: int | None = 60  # soft CPU time


class Sandbox:
    """
    Isolated execution environment with timeout and resource limits.

    Capabilities: write files, run shell commands, run tests, install dependencies.
    """

    def __init__(self, root: str | Path, limits: SandboxLimits | None = None):
        self.root = Path(root).resolve()
        self.limits = limits or SandboxLimits()

    def _cwd(self) -> Path:
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def write_file(self, path: str, content: str) -> SandboxResult:
        """Write content to a file under sandbox root. Creates parent dirs."""
        try:
            p = (self.root / path).resolve()
            if not str(p).startswith(str(self.root)):
                return SandboxResult(
                    success=False,
                    error="Path escapes sandbox root",
                )
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return SandboxResult(success=True, stdout=f"Wrote {len(content)} chars to {path}")
        except Exception as e:
            return SandboxResult(success=False, error=str(e))

    def read_file(self, path: str) -> SandboxResult:
        """Read file content under sandbox root."""
        try:
            p = (self.root / path).resolve()
            if not str(p).startswith(str(self.root)) or not p.is_file():
                return SandboxResult(success=False, error=f"File not in sandbox or missing: {path}")
            content = p.read_text(encoding="utf-8", errors="replace")
            return SandboxResult(success=True, stdout=content)
        except Exception as e:
            return SandboxResult(success=False, error=str(e))

    def run(
        self,
        command: str | list[str],
        cwd: str | Path | None = None,
        env: dict | None = None,
        timeout_seconds: int | None = None,
    ) -> SandboxResult:
        """
        Run a shell command in the sandbox with timeout and optional resource limits.
        """
        timeout = timeout_seconds or self.limits.timeout_seconds
        work_dir = Path(cwd) if cwd else self._cwd()
        if not work_dir.exists():
            work_dir.mkdir(parents=True, exist_ok=True)
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        if isinstance(command, str):
            cmd_list = shlex.split(command)
        else:
            cmd_list = list(command)

        def _set_limits() -> None:
            if resource is None:
                return
            if self.limits.max_memory_mb is not None:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_AS,
                        (self.limits.max_memory_mb * 1024 * 1024, -1),
                    )
                except (ValueError, OSError):
                    pass
            if self.limits.max_cpu_seconds is not None:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_CPU,
                        (self.limits.max_cpu_seconds, -1),
                    )
                except (ValueError, OSError):
                    pass

        try:
            proc = subprocess.run(
                cmd_list,
                cwd=str(work_dir),
                env=full_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_set_limits if os.name != "nt" else None,
            )
            out = (proc.stdout or "") + (
                "\n--- stderr ---\n" + (proc.stderr or "") if proc.stderr else ""
            )
            return SandboxResult(
                success=proc.returncode == 0,
                stdout=out.strip(),
                stderr=proc.stderr or "",
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                timed_out=True,
                error=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return SandboxResult(success=False, error=str(e))

    def install_dependencies(self, backend: bool = True, frontend: bool = False) -> SandboxResult:
        """Install backend (pip) and optionally frontend (npm) dependencies."""
        results: list[str] = []
        if backend:
            req = self.root / "backend" / "requirements.txt"
            if not req.exists():
                req = self.root / "requirements.txt"
            if req.exists():
                # Prefer uv when available (e.g. venvs without pip); else pip
                r = self.run(
                    ["uv", "pip", "install", "-r", str(req)],
                    timeout_seconds=120,
                )
                if not r.success and r.error:
                    python = os.environ.get("PYTHON") or sys.executable or "python3"
                    r = self.run(
                        [python, "-m", "pip", "install", "-r", str(req)],
                        timeout_seconds=120,
                    )
                results.append(f"pip: success={r.success}" + (f" {r.error}" if r.error else ""))
        if frontend:
            pkg = self.root / "frontend" / "package.json"
            if pkg.exists():
                r = self.run("npm install", cwd=str(self.root / "frontend"), timeout_seconds=120)
                results.append(f"npm: success={r.success}" + (f" {r.error}" if r.error else ""))
        return SandboxResult(
            success=all("success=True" in s for s in results) or not results,
            stdout="\n".join(results) or "No dependency files found",
        )

    def run_tests(self, path: str = "tests") -> SandboxResult:
        """Run tests (pytest for backend, or path to test dir)."""
        test_dir = self.root / path
        if not test_dir.exists():
            test_dir = self.root / "backend" / "tests"
        if not test_dir.exists():
            test_dir = self.root
        env = os.environ.copy()
        backend_dir = self.root / "backend"
        if backend_dir.exists():
            env["PYTHONPATH"] = str(backend_dir) + os.pathsep + env.get("PYTHONPATH", "")
        python = os.environ.get("PYTHON") or sys.executable or "python3"
        cmd = [
            python,
            "-m",
            "pytest",
            str(test_dir),
            "-v",
            "--tb=short",
        ]
        return self.run(cmd, timeout_seconds=60, env=env)
