"""Batch eval runner — runs a workflow against a dataset and collects outputs."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


def run_case(binary: str, workflow: Path, inputs: dict[str, str]) -> dict:
    """Run one eval case. Returns {inputs, output, exit_code, latency_ms, success}."""
    args = [binary, "run", str(workflow)]
    for k, v in inputs.items():
        args += ["--input", f"{k}={v}"]

    start = time.monotonic()
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "inputs": inputs,
        "output": result.stdout.strip() or result.stderr.strip(),
        "exit_code": result.returncode,
        "latency_ms": latency_ms,
        "success": result.returncode == 0,
    }


def load_dataset(path: Path) -> list[dict]:
    """Load JSONL dataset.

    Each line should be one of:
    - ``{"input": "...", "expected": "..."}`` — shorthand; "input" is wrapped as {"query": input}
    - ``{"inputs": {...}, "expected": "..."}`` — explicit multi-key inputs
    """
    cases: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                case = json.loads(line)
                # Normalize: if top-level "input" is a str, wrap as {"query": input}
                if "input" in case and isinstance(case["input"], str):
                    case.setdefault("inputs", {"query": case.pop("input")})
                cases.append(case)
    return cases


def save_results(results: list[dict], path: Path) -> None:
    """Write results as JSONL to path."""
    with open(path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
