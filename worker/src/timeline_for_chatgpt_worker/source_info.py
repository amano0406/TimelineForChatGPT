from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .contracts import RunRequest


def source_export_info(request: RunRequest) -> dict[str, Any]:
    item = request.input_items[0] if request.input_items else None
    path = Path(item.uploaded_path or item.original_path).expanduser().resolve() if item else None
    payload: dict[str, Any] = {
        "source_kind": item.source_kind if item else "unknown",
        "source_id": item.source_id if item else "unknown",
        "filename": item.display_name if item else "",
        "path": str(path) if path else "",
        "size_bytes": item.size_bytes if item else 0,
    }
    if path and path.is_file():
        payload["sha256"] = hash_file_sha256(path)
        payload["size_bytes"] = path.stat().st_size
    return payload


def hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
