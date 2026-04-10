"""WorkspaceContext — project root discovery and devsper.md loading."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceContext:
    """Resolved information about the current project workspace."""

    project_root: Path
    project_id: str        # sha256(project_root)[:16]
    project_name: str      # project_root.name
    md_content: str | None # contents of devsper.md if present
    storage_dir: Path      # ~/.local/share/devsper/projects/{project_id}/

    @classmethod
    def discover(cls, cwd: Path) -> "WorkspaceContext":
        """Walk upward from cwd to find project root.

        Priority:
        1. First directory containing devsper.md (upward from cwd, inclusive)
        2. First directory containing .git/  (upward from cwd, inclusive)
        3. cwd itself as fallback
        """
        root: Path | None = None
        md_content: str | None = None

        # Walk up looking for devsper.md first
        for parent in [cwd, *cwd.parents]:
            md_path = parent / "devsper.md"
            if md_path.is_file():
                root = parent
                md_content = md_path.read_text(encoding="utf-8")
                break

        # If not found, walk up looking for .git
        if root is None:
            for parent in [cwd, *cwd.parents]:
                if (parent / ".git").exists():
                    root = parent
                    break

        # Final fallback
        if root is None:
            root = cwd

        project_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        storage_dir = Path.home() / ".local" / "share" / "devsper" / "projects" / project_id

        return cls(
            project_root=root.resolve(),
            project_id=project_id,
            project_name=root.resolve().name,
            md_content=md_content,
            storage_dir=storage_dir,
        )
