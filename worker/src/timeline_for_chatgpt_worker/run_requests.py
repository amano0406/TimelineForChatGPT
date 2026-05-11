from __future__ import annotations

import time
import uuid
from pathlib import Path

from .contracts import InputItem, ParserOptions, RunRequest, RunStatus
from .fs_utils import ensure_dir, now_iso, slugify, write_json


def create_run_from_input(
    input_path: Path,
    output_root: Path,
    profile: str,
    run_id: str | None = None,
    source_id: str = "cli",
) -> Path:
    source_path = input_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Input does not exist: {source_path}")
    if not source_path.is_file() and not source_path.is_dir():
        raise ValueError(f"Input must be a ZIP file or extracted export directory: {source_path}")

    source_kind = "upload_zip" if source_path.is_file() else "export_dir"
    if source_kind == "upload_zip" and source_path.suffix.lower() != ".zip":
        raise ValueError(f"Input file must be a ChatGPT export ZIP: {source_path}")

    created_at = now_iso()
    resolved_run_id = run_id or build_run_id(source_path)
    run_dir = ensure_dir(output_root / resolved_run_id)

    request = RunRequest(
        schema_version=1,
        run_id=resolved_run_id,
        created_at=created_at,
        output_root_id="cli",
        output_root_path=str(output_root),
        profile=profile,
        reprocess_duplicates=False,
        parser_options=ParserOptions(),
        input_items=[
            InputItem(
                input_id="input-0001",
                source_kind=source_kind,
                source_id=source_id,
                original_path=str(source_path),
                display_name=source_path.name,
                size_bytes=source_path.stat().st_size if source_path.is_file() else 0,
                uploaded_path=str(source_path),
            )
        ],
    )
    status = RunStatus(
        run_id=resolved_run_id,
        state="pending",
        current_stage="queued",
        message="Queued from CLI.",
        updated_at=created_at,
    )

    write_json(run_dir / "request.json", request_to_dict(request))
    write_json(run_dir / "status.json", status.to_dict())
    return run_dir


def build_run_id(source_path: Path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    token = uuid.uuid4().hex[:8]
    return f"run-{stamp}-{slugify(source_path.stem)[:32]}-{token}"


def request_to_dict(request: RunRequest) -> dict[str, object]:
    return {
        "schema_version": request.schema_version,
        "run_id": request.run_id,
        "created_at": request.created_at,
        "output_root_id": request.output_root_id,
        "output_root_path": request.output_root_path,
        "profile": request.profile,
        "reprocess_duplicates": request.reprocess_duplicates,
        "parser_options": request.parser_options.to_dict(),
        "input_items": [item.to_dict() for item in request.input_items],
    }
