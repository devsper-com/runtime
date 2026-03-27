from __future__ import annotations

from devsper.export.packager import export_agent_package, run_agent_package


def run_export_package(name: str, out_dir: str) -> int:
    path = export_agent_package(name=name, out_dir=out_dir)
    print(path)
    return 0


def run_package(package_path: str, task: str) -> int:
    out = run_agent_package(package_path, task)
    for k, v in out.items():
        print(f"{k}: {v}")
    return 0
