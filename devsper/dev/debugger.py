"""
Test execution loop: run tests, detect errors, spawn fix tasks, patch code.
Loop until tests pass or max iterations.
"""

from dataclasses import dataclass, field
from typing import Callable

from devsper.dev.sandbox import Sandbox, SandboxResult


@dataclass
class DebugResult:
    """Result of the debug loop."""

    passed: bool
    iterations: int
    last_stdout: str = ""
    last_stderr: str = ""
    fixes_applied: list[str] = field(default_factory=list)


def debug_loop(
    sandbox: Sandbox,
    max_iterations: int = 5,
    test_path: str = "tests",
    get_fix: Callable[[str, str], str] | None = None,
) -> DebugResult:
    """
    Run tests in sandbox; on failure, call get_fix(stdout, stderr) to get patch/code,
    apply it (e.g. via sandbox.write_file), then re-run. Loop until tests pass or
    max_iterations. If get_fix is None, no fixes are applied (just re-run).
    """
    fixes: list[str] = []
    last_stdout = ""
    last_stderr = ""

    for iteration in range(max_iterations):
        result: SandboxResult = sandbox.run_tests(path=test_path)
        last_stdout = result.stdout
        last_stderr = result.stderr or ""

        if result.success:
            return DebugResult(
                passed=True,
                iterations=iteration + 1,
                last_stdout=last_stdout,
                last_stderr=last_stderr,
                fixes_applied=fixes,
            )

        if get_fix and not result.timed_out:
            fix_instruction = get_fix(last_stdout, last_stderr)
            if fix_instruction and fix_instruction.strip():
                fixes.append(fix_instruction[:500])
                # get_fix may return "path: <path>\\ncontent: <content>" or similar
                # A real implementation would parse and call sandbox.write_file;
                # for now we only record that a fix was requested.
                # Caller can pass a get_fix that actually writes files.
                if _apply_fix_instruction(sandbox, fix_instruction):
                    continue
        break

    return DebugResult(
        passed=False,
        iterations=max_iterations,
        last_stdout=last_stdout,
        last_stderr=last_stderr,
        fixes_applied=fixes,
    )


def _apply_fix_instruction(sandbox: Sandbox, instruction: str) -> bool:
    """
    Try to parse a fix instruction (e.g. "FILE: path\\nCONTENT: ...") and apply via sandbox.
    Returns True if something was applied.
    """
    lines = instruction.strip().split("\n")
    path = None
    content_lines: list[str] = []
    in_content = False
    for line in lines:
        if line.upper().startswith("FILE:") or line.upper().startswith("PATH:"):
            path = line.split(":", 1)[1].strip()
            in_content = False
        elif line.upper().startswith("CONTENT:") or line.upper().startswith("CODE:"):
            in_content = True
            content_lines.append(line.split(":", 1)[1] if ":" in line else "")
        elif in_content and path:
            content_lines.append(line)
    if path and content_lines:
        content = "\n".join(content_lines)
        r = sandbox.write_file(path, content)
        return r.success
    return False
