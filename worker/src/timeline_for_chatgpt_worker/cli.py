from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

from .contracts import InputItem, ParserOptions, RunRequest, RunStatus
from .fs_utils import ensure_dir, load_json, now_iso, slugify, write_json
from .master import APPLICATION_NAME, build_download_zip, rebuild_master_from_run
from .processor import outputs_root, process_pending_runs, process_run
from .refresh import (
    build_config_check,
    build_refresh_run_id,
    build_refresh_report_path,
    default_settings_path,
    discover_inputs,
    fingerprint_file,
    init_settings,
    load_refresh_state,
    load_runtime_config,
    refresh_lock,
    same_fingerprint,
    validate_runtime_config,
    write_refresh_index,
    write_refresh_latest_markdown,
    write_refresh_state,
)

HOST_CLI_ALLOW_ENV = "TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI"
DOCKER_RUNTIME_ENV = "TIMELINE_FOR_CHATGPT_DOCKER"
DEFAULT_ITEMS_LIST_PAGE_SIZE = 100


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TimelineForChatGPT worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Create and run a run for one ChatGPT export.")
    process.add_argument("input_path", help="Path to a ChatGPT export ZIP or extracted export directory.")
    process.add_argument("--output-root", help="Directory where run output folders are written.")
    process.add_argument("--profile", default="timeline-default")
    process.add_argument("--run-id", help="Optional explicit run id. Defaults to a generated run id.")
    process.add_argument("--enqueue-only", action="store_true", help="Create request/status files without processing.")

    refresh = subparsers.add_parser("refresh", help="Scan configured input roots and process changed exports.")
    refresh.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    refresh.add_argument("--config", help="Deprecated alias for --settings.")
    refresh.add_argument("--dry-run", action="store_true", help="Write a refresh report without processing runs.")
    refresh.add_argument("--force", action="store_true", help="Process every discovered input even when unchanged.")

    config_check = subparsers.add_parser("config-check", help="Validate refresh configuration without processing.")
    config_check.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    config_check.add_argument("--config", help="Deprecated alias for --settings.")

    settings = subparsers.add_parser("settings", help="Manage persistent settings.")
    settings_subparsers = settings.add_subparsers(dest="settings_command", required=True)
    settings_init = settings_subparsers.add_parser("init", help="Create settings.json if it does not exist.")
    settings_init.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_init.add_argument("--example", help="Example settings JSON path. Defaults to settings.example.json.")
    settings_status = settings_subparsers.add_parser("status", help="Show resolved settings and storage paths.")
    settings_status.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_status.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    settings_output = settings_subparsers.add_parser("output", help="Manage the fixed output root.")
    settings_output_subparsers = settings_output.add_subparsers(dest="settings_output_command", required=True)
    settings_output_show = settings_output_subparsers.add_parser("show", help="Show the resolved output root.")
    settings_output_show.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_output_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    settings_output_set = settings_output_subparsers.add_parser("set", help="Set outputRoot in settings.json.")
    settings_output_set.add_argument("path", help="New output root path.")
    settings_output_set.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_output_set.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    items = subparsers.add_parser("items", help="Refresh, list, and download ChatGPT conversation items.")
    items_subparsers = items.add_subparsers(dest="items_command", required=True)
    items_list = items_subparsers.add_parser("list", help="List current output items.")
    items_list.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_list.add_argument(
        "--page",
        type=positive_int,
        help="1-based page number. When omitted with --page-size, list returns every item.",
    )
    items_list.add_argument(
        "--page-size",
        type=positive_int,
        help=(
            f"Items per page. Defaults to {DEFAULT_ITEMS_LIST_PAGE_SIZE} when paging is requested."
        ),
    )
    items_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    items_refresh = items_subparsers.add_parser("refresh", help="Rebuild master artifacts from one ChatGPT export ZIP.")
    items_refresh.add_argument("--file", required=True, help="ChatGPT export ZIP to read.")
    items_refresh.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_refresh.add_argument("--download-to", help="Copy the generated ZIP to this directory or file path.")
    items_refresh.add_argument("--overwrite", action="store_true", help="Allow replacing an existing download ZIP.")
    items_refresh.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    items_download = items_subparsers.add_parser("download", help="Copy the latest generated ZIP.")
    items_download.add_argument("--to", required=True, help="Destination directory or ZIP file path.")
    items_download.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    items_download.add_argument("--overwrite", action="store_true", help="Allow replacing an existing ZIP.")
    items_download.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    runs = subparsers.add_parser("runs", help="Inspect refresh runs.")
    runs_subparsers = runs.add_subparsers(dest="runs_command", required=True)
    runs_list = runs_subparsers.add_parser("list", help="List known runs.")
    runs_list.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    runs_list.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    runs_show = runs_subparsers.add_parser("show", help="Show one run.")
    runs_show.add_argument("--run-id", required=True, help="Run id to inspect.")
    runs_show.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    runs_show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    daemon = subparsers.add_parser("daemon", help="Poll for pending runs.")
    daemon.add_argument("--poll-interval", type=int, default=5)

    subparsers.add_parser("run-once", help="Process pending runs once.")
    return parser


def main(argv: list[str] | None = None) -> int:
    guard_message = docker_only_cli_guard_message()
    if guard_message:
        print(guard_message, file=sys.stderr)
        return 2

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "process":
        run_dir = create_run_from_input(
            input_path=Path(args.input_path),
            output_root=Path(args.output_root) if args.output_root else outputs_root(),
            profile=str(args.profile),
            run_id=args.run_id,
        )
        if not args.enqueue_only:
            process_run(run_dir)
        print(run_dir)
        return 0

    if args.command == "refresh":
        report = refresh_from_config(
            config_path=resolve_settings_arg(args),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
        )
        print(report["report_path"])
        return 0

    if args.command == "config-check":
        report = build_config_check(resolve_settings_arg(args))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "settings" and args.settings_command == "init":
        settings_path = init_settings(
            settings_path=Path(args.settings) if args.settings else default_settings_path(),
            example_path=Path(args.example) if args.example else None,
        )
        print(settings_path)
        return 0

    if args.command == "settings" and args.settings_command == "status":
        payload = settings_status_payload(resolve_settings_arg(args))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.command == "settings" and args.settings_command == "output":
        if args.settings_output_command == "show":
            payload = settings_output_show_payload(resolve_settings_arg(args))
            print_payload(payload, bool(args.json), text_key="output_root")
            return 0
        if args.settings_output_command == "set":
            payload = settings_output_set_payload(
                settings_path=resolve_settings_arg(args),
                path_value=str(args.path),
            )
            print_payload(payload, bool(args.json), text_key="output_root")
            return 0

    if args.command == "items" and args.items_command == "list":
        paging_requested = args.page is not None or args.page_size is not None
        payload = items_list_payload(
            resolve_settings_arg(args),
            page=int(args.page or 1),
            page_size=int(args.page_size or DEFAULT_ITEMS_LIST_PAGE_SIZE),
            include_all=not paging_requested,
        )
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.command == "items" and args.items_command == "refresh":
        payload = items_refresh_from_file(
            file_path=Path(args.file),
            settings_path=resolve_settings_arg(args),
            download_to=Path(args.download_to) if args.download_to else None,
            overwrite=bool(args.overwrite),
        )
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.command == "items" and args.items_command == "download":
        payload = items_download_latest(
            settings_path=resolve_settings_arg(args),
            destination=Path(args.to),
            overwrite=bool(args.overwrite),
        )
        print_payload(payload, bool(args.json), text_key="download_path")
        return 0

    if args.command == "runs" and args.runs_command == "list":
        payload = runs_list_payload(resolve_settings_arg(args))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.command == "runs" and args.runs_command == "show":
        payload = runs_show_payload(resolve_settings_arg(args), str(args.run_id))
        print_payload(payload, bool(args.json), text_key="summary")
        return 0

    if args.command == "run-once":
        process_pending_runs()
        return 0

    while True:
        process_pending_runs()
        time.sleep(max(1, int(args.poll_interval)))


def docker_only_cli_guard_message(is_docker_file: bool | None = None) -> str | None:
    detected_docker_file = Path("/.dockerenv").exists() if is_docker_file is None else is_docker_file
    if truthy_env(DOCKER_RUNTIME_ENV) or detected_docker_file:
        return None
    if truthy_env(HOST_CLI_ALLOW_ENV):
        return None
    return (
        "TimelineForChatGPT CLI is Docker-only. "
        "Run it with `docker compose exec -T worker python -m timeline_for_chatgpt_worker <command>`, "
        f"or set {HOST_CLI_ALLOW_ENV}=1 for tests only."
    )


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return parsed


def resolve_settings_arg(args: argparse.Namespace) -> Path:
    value = getattr(args, "settings", None) or getattr(args, "config", None)
    return Path(value) if value else default_settings_path()


def print_payload(payload: dict[str, object], json_output: bool, text_key: str | None = None) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    value = payload.get(text_key or "") if text_key else None
    if isinstance(value, str):
        print(value)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def settings_status_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    warnings = validate_runtime_config(config, require_input_roots=False)
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "output_root": str(config.output_root),
        "run_root": str(config.run_root),
        "state_root": str(config.state_root),
        "cache_root": str(config.cache_root),
        "warnings": warnings,
        "summary": (
            f"output={config.output_root} runs={config.run_root} "
            f"state={config.state_root} cache={config.cache_root}"
        ),
    }


def settings_output_show_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "output_root": str(config.output_root),
    }


def settings_output_set_payload(settings_path: Path, path_value: str) -> dict[str, object]:
    payload = load_json(settings_path)
    if not isinstance(payload, dict):
        raise ValueError(f"settings must be a JSON object: {settings_path}")
    payload.clear()
    payload["outputRoot"] = path_value
    write_json(settings_path, payload)
    return settings_output_show_payload(settings_path)


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


def runs_list_payload(settings_path: Path) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    runs: list[dict[str, object]] = []
    if config.run_root.exists():
        for run_dir in sorted(config.run_root.glob("run-*")):
            status_path = run_dir / "status.json"
            result_path = run_dir / "result.json"
            status = load_json(status_path) if status_path.exists() else {}
            result = load_json(result_path) if result_path.exists() else {}
            runs.append(
                {
                    "run_id": run_dir.name,
                    "state": result.get("state") or status.get("state") or "unknown",
                    "run_dir": str(run_dir),
                    "completed_at": status.get("completed_at"),
                    "processed_count": result.get("processed_count"),
                }
            )
    return {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "run_root": str(config.run_root),
        "run_count": len(runs),
        "runs": runs,
        "summary": f"{len(runs)} runs",
    }


def runs_show_payload(settings_path: Path, run_id: str) -> dict[str, object]:
    config = load_runtime_config(settings_path)
    run_dir = (config.run_root / run_id).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"Run does not exist: {run_dir}")
    payload: dict[str, object] = {
        "schema_version": 1,
        "settings_path": str(settings_path),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "summary": str(run_dir),
    }
    for name in ("request", "status", "result", "manifest"):
        path = run_dir / f"{name}.json"
        payload[name] = load_json(path) if path.exists() else None
    return payload


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


def refresh_from_config(config_path: Path, dry_run: bool = False, force: bool = False) -> dict[str, object]:
    refresh_started_perf = time.perf_counter()
    config = load_runtime_config(config_path)
    warnings = validate_runtime_config(config)
    started_at = now_iso()
    ensure_dir(config.run_root)
    ensure_dir(config.state_root)
    with refresh_lock(config.state_root):
        state = load_refresh_state(config.state_root)
        state_items = state.setdefault("items", {})
        report_items: list[dict[str, object]] = []
        processed = 0
        skipped = 0
        failed = 0
        missing = 0
        duplicate = 0
        fingerprint_seconds_total = 0.0
        processing_seconds_total = 0.0

        discovery_started_perf = time.perf_counter()
        discovered_rows = discover_inputs(config)
        discovery_seconds = elapsed_seconds(discovery_started_perf)
        discovered_keys = {str(input_path) for _, input_path in discovered_rows}
        seen_sha: dict[str, dict[str, object]] = {}

        for key, previous in sorted(state_items.items()):
            if key in discovered_keys or not isinstance(previous, dict):
                continue
            missing += 1
            report_items.append(
                {
                    "input_root_id": previous.get("input_root_id"),
                    "input_path": key,
                    "status": "missing_from_input",
                    "previous_run_dir": previous.get("run_dir"),
                    "result_state": previous.get("result_state"),
                    "fingerprint": previous.get("fingerprint"),
                }
            )

        for input_root, input_path in discovered_rows:
            key = str(input_path)
            previous = state_items.get(key) if isinstance(state_items.get(key), dict) else {}
            fingerprint_started_perf = time.perf_counter()
            fingerprint = fingerprint_file(input_path, previous)
            fingerprint_seconds = elapsed_seconds(fingerprint_started_perf)
            fingerprint_seconds_total += fingerprint_seconds
            sha256 = str(fingerprint.get("sha256") or "")
            if sha256 and sha256 in seen_sha and not force:
                duplicate += 1
                skipped += 1
                first_seen = seen_sha[sha256]
                report_items.append(
                    {
                        "input_root_id": input_root.root_id,
                        "input_path": str(input_path),
                        "status": "duplicate_skipped",
                        "duplicate_of": first_seen.get("input_path"),
                        "duplicate_run_dir": first_seen.get("run_dir") or first_seen.get("previous_run_dir"),
                        "fingerprint": fingerprint,
                        "timing": {
                            "fingerprint_seconds": fingerprint_seconds,
                            "processing_seconds": 0.0,
                        },
                    }
                )
                continue

            previous_fingerprint = (previous or {}).get("fingerprint") or {}
            previous_state = str((previous or {}).get("result_state") or "")
            previous_run_dir = Path(str((previous or {}).get("run_dir") or ""))
            unchanged = same_fingerprint(fingerprint, previous_fingerprint)
            can_skip = (
                unchanged
                and not force
                and previous_state in {"completed", "failed"}
                and previous_run_dir.exists()
            )

            if can_skip:
                skipped += 1
                item = {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "skipped_unchanged",
                    "previous_run_dir": str(previous_run_dir),
                    "result_state": previous_state,
                    "fingerprint": fingerprint,
                    "timing": {
                        "fingerprint_seconds": fingerprint_seconds,
                        "processing_seconds": 0.0,
                    },
                }
                report_items.append(item)
                if sha256:
                    seen_sha[sha256] = item
                continue

            run_id = build_refresh_run_id(input_root.root_id, input_path, fingerprint, started_at)
            if dry_run:
                skipped += 1
                item = {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "would_process",
                    "run_id": run_id,
                    "fingerprint": fingerprint,
                    "timing": {
                        "fingerprint_seconds": fingerprint_seconds,
                        "processing_seconds": 0.0,
                    },
                }
                report_items.append(item)
                if sha256:
                    seen_sha[sha256] = item
                continue

            run_dir = create_run_from_input(
                input_path=input_path,
                output_root=config.run_root,
                profile=config.profile,
                run_id=run_id,
                source_id=input_root.root_id,
            )
            processing_started_perf = time.perf_counter()
            process_run(run_dir)
            processing_seconds = elapsed_seconds(processing_started_perf)
            processing_seconds_total += processing_seconds
            status_payload = load_json(run_dir / "status.json")
            result_payload = load_json(run_dir / "result.json")
            result_state = str(result_payload.get("state") or status_payload.get("state") or "unknown")
            if result_state == "completed":
                processed += 1
            else:
                failed += 1

            updated_at = now_iso()
            state_entry = {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "display_name": input_path.name,
                "fingerprint": fingerprint,
                "run_dir": str(run_dir),
                "run_id": run_id,
                "result_state": result_state,
                "updated_at": updated_at,
            }
            if result_state == "completed":
                state_entry["latest_success_run_dir"] = str(run_dir)
                state_entry["latest_success_run_id"] = run_id
                state_entry["latest_success_at"] = updated_at
            elif isinstance(previous, dict):
                for success_key in ("latest_success_run_dir", "latest_success_run_id", "latest_success_at"):
                    if previous.get(success_key):
                        state_entry[success_key] = previous[success_key]
            state_items[key] = state_entry
            item = {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "status": result_state,
                "run_dir": str(run_dir),
                "run_id": run_id,
                "fingerprint": fingerprint,
                "message": status_payload.get("message"),
                "timing": {
                    "fingerprint_seconds": fingerprint_seconds,
                    "processing_seconds": processing_seconds,
                },
            }
            report_items.append(item)
            if sha256:
                seen_sha[sha256] = item

        completed_at = now_iso()
        state["updated_at"] = completed_at
        if not dry_run:
            write_refresh_state(config.state_root, state)

        report_path = build_refresh_report_path(config.run_root, started_at)
        report = {
            "schema_version": 1,
            "started_at": started_at,
            "completed_at": completed_at,
            "config_path": str(config_path),
            "output_root": str(config.output_root),
            "run_root": str(config.run_root),
            "state_root": str(config.state_root),
            "dry_run": dry_run,
            "force": force,
            "warnings": warnings,
            "summary": {
                "discovered": len(discovered_rows),
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "missing": missing,
                "duplicates": duplicate,
                "duration_seconds": elapsed_seconds(refresh_started_perf),
                "discovery_seconds": discovery_seconds,
                "fingerprint_seconds": round(fingerprint_seconds_total, 6),
                "processing_seconds": round(processing_seconds_total, 6),
            },
            "items": report_items,
            "report_path": str(report_path),
        }
        latest_path = config.run_root / "refresh-latest.md"
        report["latest_markdown_path"] = str(latest_path)
        index_json_path = config.run_root / "index.json"
        index_markdown_path = config.run_root / "index.md"
        report["index_json_path"] = str(index_json_path)
        report["index_markdown_path"] = str(index_markdown_path)
        write_json(report_path, report)
        write_refresh_latest_markdown(config.run_root, report)
        write_refresh_index(config.run_root, state, report)
        return report


def elapsed_seconds(started_perf: float) -> float:
    return round(time.perf_counter() - started_perf, 6)


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


if __name__ == "__main__":
    raise SystemExit(main())
