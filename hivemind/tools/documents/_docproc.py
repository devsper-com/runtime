"""Shared helper for docproc CLI: run docproc and read output. Optional dependency."""

import subprocess
import tempfile
from pathlib import Path


DOCPROC_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx"}


def docproc_available() -> bool:
    """Return True if docproc CLI is available."""
    try:
        subprocess.run(
            ["docproc", "--help"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_docproc_to_markdown(file_path: str) -> tuple[str, str | None]:
    """
    Run docproc --file <path> -o <tmp>.md and read the markdown.
    Returns (content, None) on success or ("", error_message) on failure.
    """
    path = Path(file_path).resolve()
    if not path.exists() or not path.is_file():
        return "", f"File not found: {file_path}"
    if path.suffix.lower() not in DOCPROC_EXTENSIONS:
        return "", f"Unsupported format. Use one of: {DOCPROC_EXTENSIONS}"
    if not docproc_available():
        return "", "docproc not installed. Install with: pip install docproc"
    try:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            out_path = f.name
        try:
            result = subprocess.run(
                ["docproc", "--file", str(path), "-o", out_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                err = result.stderr or result.stdout or "Unknown error"
                return "", f"docproc failed: {err}"
            content = Path(out_path).read_text(encoding="utf-8", errors="replace")
            return content, None
        finally:
            Path(out_path).unlink(missing_ok=True)
    except subprocess.TimeoutExpired:
        return "", "docproc timed out"
    except Exception as e:
        return "", str(e)
