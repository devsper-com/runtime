"""Search for files by name pattern or content."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class SearchFilesTool(Tool):
    """Search for files: by filename pattern (glob) or by text content in files."""

    name = "search_files"
    description = "Search for files by path/name pattern or by content. Returns matching file paths."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory to search"},
            "pattern": {"type": "string", "description": "Glob pattern for filename (e.g. *.py) or regex for content"},
            "content_search": {"type": "boolean", "description": "If true, pattern is used as regex to search file contents"},
        },
        "required": ["path", "pattern"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        pattern = kwargs.get("pattern")
        content_search = kwargs.get("content_search", False)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not pattern or not isinstance(pattern, str):
            return "Error: pattern must be a non-empty string"
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return f"Error: path must be an existing directory: {path}"
        try:
            if content_search:
                try:
                    rx = re.compile(pattern)
                except re.error:
                    return f"Error: invalid regex pattern: {pattern}"
                results = []
                for f in p.rglob("*"):
                    if f.is_file():
                        try:
                            text = f.read_text(encoding="utf-8", errors="replace")
                            if rx.search(text):
                                results.append(str(f))
                        except (OSError, UnicodeDecodeError):
                            pass
                return "\n".join(sorted(results)) if results else "No matches found"
            else:
                matches = sorted(p.rglob(pattern))
                files = [str(m) for m in matches if m.is_file()]
                return "\n".join(files) if files else "No matches found"
        except Exception as e:
            return f"Error searching: {e}"


register(SearchFilesTool())
