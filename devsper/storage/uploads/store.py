from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path


def uploads_root() -> Path:
    base = os.environ.get("DEVSPER_UPLOADS_DIR", "").strip()
    if base:
        root = Path(base)
    else:
        root = Path(__file__).resolve().parents[3] / "storage" / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(local_path: str, *, filename: str | None = None) -> dict:
    src = Path(local_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"File not found: {local_path}")
    upload_id = uuid.uuid4().hex
    safe_name = (filename or src.name or "upload.bin").replace("/", "_")
    target = uploads_root() / f"{upload_id}_{safe_name}"
    shutil.copy2(src, target)
    return {
        "upload_id": upload_id,
        "filename": safe_name,
        "path": str(target),
        "size_bytes": int(target.stat().st_size),
    }


def resolve_upload(upload_id: str) -> Path | None:
    root = uploads_root()
    prefix = f"{upload_id}_"
    for p in root.iterdir():
        if p.is_file() and p.name.startswith(prefix):
            return p
    return None

