"""Surgical find-and-replace tool for the coding REPL."""

import difflib
import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class StrReplaceFile(Tool):
    """Replace an exact string in a file exactly once. Returns a JSON diff."""

    name = "str_replace_file"
    description = (
        "Surgically replace an exact string in a file. "
        "old_str must appear exactly once. Returns a unified diff."
    )
    category = "workspace"
    input_schema = {
        "file": {"type": "string", "description": "Path to the file (relative or absolute)"},
        "old_str": {"type": "string", "description": "The exact string to replace (must appear once)"},
        "new_str": {"type": "string", "description": "The replacement string"},
    }

    def run(self, **kwargs) -> str:
        """Execute a surgical string replacement in a file.

        Args:
            **kwargs: Must contain 'file', 'old_str', and 'new_str'.

        Returns:
            JSON string with diff result or error message.
        """
        file: str = kwargs["file"]
        old_str: str = kwargs["old_str"]
        new_str: str = kwargs["new_str"]

        path = Path(file) if Path(file).is_absolute() else Path.cwd() / file
        try:
            original = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return json.dumps({"error": f"file not found: {file}"})

        count = original.count(old_str)
        if count == 0:
            return json.dumps({"error": "old_str not found in file"})
        if count > 1:
            return json.dumps({"error": "old_str matches multiple locations — be more specific"})

        updated = original.replace(old_str, new_str, 1)
        path.write_text(updated, encoding="utf-8")

        original_lines = original.splitlines(keepends=True)
        updated_lines = updated.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                updated_lines,
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
                n=3,
            )
        )
        diff_str = "".join(diff_lines)
        added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

        return json.dumps({
            "file": str(path),
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_str,
        })


register(StrReplaceFile())
