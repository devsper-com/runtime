from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path

from devsper.export.manifest import build_manifest


def export_agent_package(name: str, out_dir: str = "./dist") -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pkg_path = out / f"{name}.devsper"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        cfg = Path("devsper.toml")
        wf = Path("workflow.devsper.toml")
        if cfg.exists():
            (t / "devsper.toml").write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")
        if wf.exists():
            (t / "workflow.devsper.toml").write_text(wf.read_text(encoding="utf-8"), encoding="utf-8")
        (t / "README.md").write_text(f"# {name}\n\nPackaged with devsper export.\n", encoding="utf-8")
        (t / "requirements.txt").write_text("devsper\n", encoding="utf-8")
        ex = t / "examples"
        ex.mkdir(exist_ok=True)
        (ex / "sample.json").write_text(json.dumps({"input": "example", "output": "example"}, indent=2), encoding="utf-8")
        manifest = build_manifest(
            name=name,
            devsper_version="2.x",
            agents=[],
            tools_required=[],
            models_required=[],
            avg_cost_per_run_usd=0.0,
            avg_duration_s=0.0,
        )
        (t / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(t):
                for fn in files:
                    p = Path(root) / fn
                    zf.write(p, p.relative_to(t))
    return str(pkg_path)


def run_agent_package(package_path: str, task: str) -> dict:
    from devsper.swarm.swarm import Swarm

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(t)
        cfg = t / "devsper.toml"
        swarm = Swarm(config=str(cfg) if cfg.exists() else None)
        return dict(swarm.run(task))
