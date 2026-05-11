from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .fs_utils import ensure_dir, load_json, now_iso, write_json
from .master import APPLICATION_NAME, build_download_zip, rebuild_master_from_run
from .processor import process_run
from .refresh import load_runtime_config, refresh_lock, validate_runtime_config
from .run_requests import create_run_from_input

DEFAULT_ITEMS_LIST_PAGE_SIZE = 100


def items_refresh_from_file(
    file_path: Path,
    settings_path: Path,
    download_to: Path | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    warnings = validate_runtime_config(config, require_input_roots=False)
    ensure_dir(config.output_root)
    ensure_dir(config.state_root)
    ensure_dir(config.run_root)

    with refresh_lock(config.state_root):
        run_dir = create_run_from_input(
            input_path=file_path,
            output_root=config.run_root,
            profile=config.profile,
            source_id="file",
        )
        started_at = now_iso()
        process_run(run_dir)
        status = load_json(run_dir / "status.json")
        result = load_json(run_dir / "result.json")
        if str(result.get("state") or status.get("state") or "").lower() != "completed":
            raise RuntimeError(str(status.get("message") or result.get("warnings") or "refresh failed"))

        manifest = rebuild_master_from_run(run_dir, config.output_root)
        download_zip_path = Path(str(manifest["download_zip_path"]))
        copied_download_path = (
            copy_download_zip(download_zip_path, download_to, overwrite=overwrite)
            if download_to
            else None
        )

        completed_at = now_iso()
        current = {
            "schema_version": 1,
            "application": "TimelineForChatGPT",
            "run_id": result.get("run_id") or status.get("run_id"),
            "state": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "settings_path": str(settings_path),
            "source_export": manifest.get("source_export"),
            "output_root": str(config.output_root),
            "run_root": str(config.run_root),
            "run_dir": str(run_dir),
            "download_zip_path": str(download_zip_path),
            "copied_download_path": str(copied_download_path) if copied_download_path else None,
            "item_count": manifest.get("item_count", 0),
            "warnings": warnings,
        }
        write_json(config.run_root / "current.json", current)
        append_jsonl(config.run_root / "refresh-history.jsonl", current)

    return {
        "schema_version": 1,
        "state": "completed",
        "summary": (
            f"refreshed {current['item_count']} conversations; "
            f"output={current['output_root']}; download={current['download_zip_path']}"
        ),
        "current": current,
        "manifest": manifest,
    }


def items_list_payload(
    settings_path: Path,
    page: int | None = None,
    page_size: int | None = None,
    include_all: bool = False,
) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    manifest_path = config.output_root / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {
        "schema_version": 1,
        "application": "TimelineForChatGPT",
        "item_count": 0,
        "items": [],
    }
    manifest_items = manifest.get("items") or []
    items = sort_items_latest_first([item for item in manifest_items if isinstance(item, dict)])
    total_items = len(items)
    item_count = int(manifest.get("item_count") or total_items)
    paging_requested = page is not None or page_size is not None
    include_all = include_all or not paging_requested
    if include_all:
        page_items = items
        pagination = {
            "mode": "all",
            "page": None,
            "page_size": None,
            "total_items": total_items,
            "total_pages": 1 if total_items else 0,
            "returned_items": len(page_items),
            "offset": 0,
            "range_start": 1 if page_items else 0,
            "range_end": len(page_items),
            "has_previous": False,
            "has_next": False,
        }
        summary = f"{item_count} conversations in output; showing all {len(page_items)} latest-first"
    else:
        page = max(1, page or 1)
        page_size = max(1, page_size or DEFAULT_ITEMS_LIST_PAGE_SIZE)
        total_pages = (total_items + page_size - 1) // page_size if total_items else 0
        offset = (page - 1) * page_size
        page_items = items[offset : offset + page_size]
        range_start = offset + 1 if page_items else 0
        range_end = offset + len(page_items) if page_items else 0
        pagination = {
            "mode": "page",
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "returned_items": len(page_items),
            "offset": offset,
            "range_start": range_start,
            "range_end": range_end,
            "has_previous": page > 1 and total_items > 0,
            "has_next": page < total_pages,
        }
        if page_items:
            summary = (
                f"{item_count} conversations in output; showing {range_start}-{range_end} "
                f"of {total_items} latest-first (page {page}/{total_pages})"
            )
        else:
            summary = f"{item_count} conversations in output; no items on page {page}"
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "output_root": str(config.output_root),
        "item_count": item_count,
        "total_items": total_items,
        "pagination": pagination,
        "sort": {
            "order": "desc",
            "fields": ["updated_at", "ended_at_utc", "created_at", "started_at_utc", "conversation_id"],
        },
        "items": page_items,
        "summary": summary,
    }


def sort_items_latest_first(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        items,
        key=lambda item: (
            item_latest_timestamp(item),
            str(item.get("conversation_id") or item.get("id") or ""),
        ),
        reverse=True,
    )


def item_latest_timestamp(item: dict[str, object]) -> float:
    for key in ("updated_at", "ended_at_utc", "created_at", "started_at_utc"):
        parsed = parse_sort_timestamp(item.get(key))
        if parsed is not None:
            return parsed
    return float("-inf")


def parse_sort_timestamp(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def items_download_latest(settings_path: Path, destination: Path, overwrite: bool = False) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    manifest_path = config.output_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No output manifest exists: {manifest_path}")
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"output manifest must be a JSON object: {manifest_path}")
    copied = build_download_zip(
        master_root=config.output_root,
        destination=resolve_download_destination_from_manifest(destination, manifest, overwrite=overwrite),
        manifest=manifest,
    )
    return {
        "schema_version": 1,
        "source_output_root": str(config.output_root),
        "download_path": str(copied),
    }


def copy_download_zip(source: Path, destination: Path, overwrite: bool = False) -> Path:
    resolved_source = source.expanduser().resolve()
    destination = destination.expanduser()
    if destination.suffix.lower() == ".zip":
        target = destination.resolve()
        ensure_dir(target.parent)
    else:
        target_dir = ensure_dir(destination.resolve())
        target = target_dir / resolved_source.name
    if target.exists() and not overwrite:
        raise FileExistsError(f"Download target already exists: {target}")
    shutil.copyfile(resolved_source, target)
    return target


def resolve_download_destination_from_manifest(
    destination: Path,
    manifest: dict[str, object],
    overwrite: bool = False,
) -> Path:
    destination = destination.expanduser()
    run_id = str(manifest.get("run_id") or "latest")
    filename = f"{APPLICATION_NAME}-export-{run_id}.zip"
    if destination.suffix.lower() == ".zip":
        target = destination.resolve()
        ensure_dir(target.parent)
    else:
        target_dir = ensure_dir(destination.resolve())
        target = target_dir / filename
    if target.exists() and not overwrite:
        raise FileExistsError(f"Download target already exists: {target}")
    return target


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
