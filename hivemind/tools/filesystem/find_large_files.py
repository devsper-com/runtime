"""Find files larger than a given size."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class FindLargeFilesTool(Tool):
    """Find files under a directory that are larger than a given size in bytes."""

    name = "find_large_files"
    description = "Find files larger than min_size bytes in a directory. Returns paths and sizes."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory to search"},
            "min_size": {"type": "integer", "description": "Minimum file size in bytes"},
        },
        "required": ["path", "min_size"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        min_size = kwargs.get("min_size")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(min_size, int) or min_size < 0:
            return "Error: min_size must be a non-negative integer"
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return f"Error: path must be an existing directory: {path}"
        try:
            results = []
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        size = f.stat().st_size
                        if size >= min_size:
                            results.append((str(f), size))
                    except OSError:
                        pass
            results.sort(key=lambda x: -x[1])
            lines = [f"{size}\t{fp}" for fp, size in results]
            return "\n".join(lines) if lines else "No files found"
        except Exception as e:
            return f"Error: {e}"


register(FindLargeFilesTool())
