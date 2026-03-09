"""
TUI Dev View: repository tree, test results, file changes.

Shown in dashboard when working with the autonomous application builder.
"""

from pathlib import Path

from textual.widgets import Static
from textual.reactive import reactive


def _tree_for_path(root: Path, max_depth: int = 4, max_entries: int = 80) -> list[str]:
    """Build a simple tree of relative paths under root."""
    lines: list[str] = []
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        return ["(no directory)"]

    def walk(p: Path, prefix: str, depth: int) -> None:
        if len(lines) >= max_entries or depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for i, e in enumerate(entries):
                if e.name.startswith(".") or e.name == "__pycache__":
                    continue
                if len(lines) >= max_entries:
                    return
                is_last = i == len(entries) - 1
                branch = "└── " if is_last else "├── "
                lines.append(prefix + branch + e.name)
                if e.is_dir():
                    ext = "    " if is_last else "│   "
                    walk(e, prefix + ext, depth + 1)
        except OSError:
            pass

    walk(root, "", 0)
    return lines if lines else ["(empty)"]


class DevView(Static):
    """
    Panel showing repository tree, test results, and file changes for build output.
    """

    repo_path: reactive[str | None] = reactive(None)
    test_results: reactive[str] = reactive("")
    file_changes: reactive[list[str]] = reactive(list)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._repo_path: str | None = None
        self._test_results = ""
        self._file_changes: list[str] = []

    def set_repo_path(self, path: str | None) -> None:
        self._repo_path = path
        self.repo_path = path

    def set_test_results(self, text: str) -> None:
        self._test_results = text
        self.test_results = text

    def set_file_changes(self, changes: list[str]) -> None:
        self._file_changes = changes
        self.file_changes = changes

    def watch_repo_path(self, path: str | None) -> None:
        self._repo_path = path
        self._refresh()

    def watch_test_results(self, text: str) -> None:
        self._test_results = text
        self._refresh()

    def watch_file_changes(self, changes: list[str]) -> None:
        self._file_changes = changes or []
        self._refresh()

    def _refresh(self) -> None:
        lines = ["Dev — Build output", ""]
        if self._repo_path:
            root = Path(self._repo_path)
            lines.append("Repository tree:")
            lines.extend(_tree_for_path(root))
            lines.append("")
        else:
            lines.append("Repository: (none — run 'hivemind build \"app\"' to generate)")
            lines.append("")

        lines.append("Test results:")
        lines.append(self._test_results[:1500] if self._test_results else "(no results)")
        lines.append("")
        lines.append("File changes:")
        for c in (self._file_changes or [])[:20]:
            lines.append(f"  {c}")
        self.update("\n".join(lines))
