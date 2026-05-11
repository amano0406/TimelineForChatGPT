from __future__ import annotations

import os
import shutil
from pathlib import Path

from .fs_utils import ensure_dir


def replace_directory(path: Path) -> None:
    ensure_safe_replace_root(path)
    ensure_dir(path)
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def ensure_safe_replace_root(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor) or str(resolved) in {"/", "/mnt", "/mnt/c"}:
        raise ValueError(f"Refusing to replace unsafe outputRoot: {resolved}")
    configured_output_root = os.environ.get("TIMELINE_FOR_CHATGPT_OUTPUT_ROOT")
    if configured_output_root:
        configured = Path(configured_output_root).expanduser().resolve()
        if resolved == configured:
            return
    if len(resolved.parts) < 4:
        raise ValueError(f"Refusing to replace too-shallow outputRoot: {resolved}")
