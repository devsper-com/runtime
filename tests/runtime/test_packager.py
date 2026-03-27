from pathlib import Path

from devsper.export.packager import export_agent_package


def test_export_agent_package(tmp_path: Path):
    pkg = export_agent_package("test-agent", out_dir=str(tmp_path))
    assert pkg.endswith(".devsper")
    assert Path(pkg).exists()
