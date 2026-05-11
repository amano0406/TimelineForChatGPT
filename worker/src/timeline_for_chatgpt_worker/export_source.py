from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .contracts import RunRequest
from .fs_utils import ensure_dir, load_json


def prepare_export_root(run_dir: Path, request: RunRequest) -> tuple[Path, str, Path | None]:
    input_item = request.input_items[0]
    uploaded_path = Path(input_item.uploaded_path or "")
    if input_item.source_kind == "upload_zip":
        extraction_root = build_short_extraction_root(uploaded_path, request.run_id)
        if extraction_root.exists():
            shutil.rmtree(extraction_root, ignore_errors=True)
        ensure_dir(extraction_root)
        try:
            with zipfile.ZipFile(uploaded_path) as archive:
                archive.extractall(extraction_root)
        except zipfile.BadZipFile as exc:
            raise ValueError(
                "The ChatGPT export ZIP is corrupted or incomplete. "
                "Older downloads in Downloads may be truncated and miss the central directory."
            ) from exc
        export_root = resolve_export_root(extraction_root)
        if not has_export_signature(export_root):
            raise ValueError("The extracted ZIP does not look like a ChatGPT export.")
        return export_root, input_item.display_name, extraction_root

    source_path = Path(input_item.uploaded_path or input_item.original_path)
    if source_path.is_dir():
        if not has_export_signature(source_path):
            raise ValueError("The selected directory does not look like a ChatGPT export.")
        return source_path, input_item.display_name, None

    raise ValueError(f"Unsupported input kind: {input_item.source_kind}")


def build_short_extraction_root(uploaded_path: Path, run_id: str) -> Path:
    run_token = run_id.rsplit("-", 1)[-1] or "run"
    anchor = uploaded_path.anchor.rstrip("\\/")
    if anchor.endswith(":"):
        return Path(f"{anchor}\\") / "t" / run_token

    temp_root = Path(tempfile.gettempdir())
    temp_anchor = temp_root.anchor.rstrip("\\/")
    if temp_anchor.endswith(":"):
        return Path(f"{temp_anchor}\\") / "t" / run_token

    return temp_root / "t" / run_token


def resolve_export_root(root: Path) -> Path:
    if has_export_signature(root):
        return root

    children = [child for child in root.iterdir() if child.is_dir()]
    if len(children) == 1 and has_export_signature(children[0]):
        return children[0]

    return root


def has_export_signature(path: Path) -> bool:
    if (path / "export_manifest.json").exists():
        return True
    return any(candidate.name.startswith("conversations") and candidate.suffix == ".json" for candidate in path.glob("*.json"))


def discover_conversation_files(export_root: Path) -> list[Path]:
    rows: list[Path] = []
    for candidate in sorted(export_root.glob("*.json")):
        name = candidate.name.lower()
        if name == "conversations.json" or (
            name.startswith("conversations-") and name.endswith(".json")
        ):
            rows.append(candidate)
    return rows


def load_conversations(export_root: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    files = discover_conversation_files(export_root)
    for path in files:
        payload = load_json(path)
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
    return rows, len(files)


def try_load_analysis_summary(export_root: Path) -> dict[str, Any]:
    path = export_root / "analysis_summary.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}
