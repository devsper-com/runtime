"""Estimate test coverage: ratio of test files to source files and test/source layout."""

from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class TestCoverageEstimatorTool(Tool):
    """
    Estimate test coverage heuristically: count test files vs source files and list test dirs.
    """

    name = "test_coverage_estimator"
    description = "Estimate test coverage: test file count vs source file count and layout."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path of the repo"},
            "test_dir_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Dir names that indicate tests (default: tests, test)",
            },
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        test_dir_names = kwargs.get("test_dir_names") or ["tests", "test"]
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        test_dirs = set(n.lower() for n in test_dir_names if isinstance(n, str))
        source_files = []
        test_files = []
        for p in root.rglob("*.py"):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            parts = [x.lower() for x in rel.parts]
            is_test = any(d in parts for d in test_dirs) or rel.name.startswith("test_") or rel.name.endswith("_test.py")
            if is_test:
                test_files.append(str(rel))
            else:
                source_files.append(str(rel))
        ratio = len(test_files) / len(source_files) if source_files else 0
        lines = [
            "Test coverage estimate",
            "=" * 40,
            f"Source files: {len(source_files)}",
            f"Test files: {len(test_files)}",
            f"Ratio (test/source): {ratio:.2f}",
            "Test dirs/files (sample): " + ", ".join(test_files[:15]),
        ]
        return "\n".join(lines)


register(TestCoverageEstimatorTool())
