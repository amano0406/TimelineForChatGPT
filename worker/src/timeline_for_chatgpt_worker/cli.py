from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import uuid

from .contracts import InputItem, JobRequest, JobStatus, ParserOptions
from .fs_utils import ensure_dir, load_json, now_iso, slugify, write_json
from .processor import outputs_root, process_job, process_pending_jobs
from .refresh import (
    build_config_check,
    build_refresh_job_id,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TimelineForChatGPT worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Create and run a job for one ChatGPT export.")
    process.add_argument("input_path", help="Path to a ChatGPT export ZIP or extracted export directory.")
    process.add_argument("--output-root", help="Directory where job output folders are written.")
    process.add_argument("--profile", default="timeline-default")
    process.add_argument("--job-id", help="Optional explicit job id. Defaults to a generated job id.")
    process.add_argument("--enqueue-only", action="store_true", help="Create request/status files without processing.")

    refresh = subparsers.add_parser("refresh", help="Scan configured input roots and process changed exports.")
    refresh.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    refresh.add_argument("--config", help="Deprecated alias for --settings.")
    refresh.add_argument("--dry-run", action="store_true", help="Write a refresh report without processing jobs.")
    refresh.add_argument("--force", action="store_true", help="Process every discovered input even when unchanged.")

    config_check = subparsers.add_parser("config-check", help="Validate refresh configuration without processing.")
    config_check.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    config_check.add_argument("--config", help="Deprecated alias for --settings.")

    settings = subparsers.add_parser("settings", help="Manage persistent settings.")
    settings_subparsers = settings.add_subparsers(dest="settings_command", required=True)
    settings_init = settings_subparsers.add_parser("init", help="Create settings.json if it does not exist.")
    settings_init.add_argument("--settings", help="Settings JSON path. Defaults to settings.json.")
    settings_init.add_argument("--example", help="Example settings JSON path. Defaults to settings.example.json.")

    daemon = subparsers.add_parser("daemon", help="Poll for pending jobs.")
    daemon.add_argument("--poll-interval", type=int, default=5)

    subparsers.add_parser("run-once", help="Process pending jobs once.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "process":
        run_dir = create_job_from_input(
            input_path=Path(args.input_path),
            output_root=Path(args.output_root) if args.output_root else outputs_root(),
            profile=str(args.profile),
            job_id=args.job_id,
        )
        if not args.enqueue_only:
            process_job(run_dir)
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

    if args.command == "run-once":
        process_pending_jobs()
        return 0

    while True:
        process_pending_jobs()
        time.sleep(max(1, int(args.poll_interval)))


def resolve_settings_arg(args: argparse.Namespace) -> Path:
    value = getattr(args, "settings", None) or getattr(args, "config", None)
    return Path(value) if value else default_settings_path()


def create_job_from_input(
    input_path: Path,
    output_root: Path,
    profile: str,
    job_id: str | None = None,
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
    resolved_job_id = job_id or build_job_id(source_path)
    run_dir = ensure_dir(output_root / resolved_job_id)

    request = JobRequest(
        schema_version=1,
        job_id=resolved_job_id,
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
    status = JobStatus(
        job_id=resolved_job_id,
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
    ensure_dir(config.output_root)
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

            job_id = build_refresh_job_id(input_root.root_id, input_path, fingerprint, started_at)
            if dry_run:
                skipped += 1
                item = {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "would_process",
                    "job_id": job_id,
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

            run_dir = create_job_from_input(
                input_path=input_path,
                output_root=config.output_root,
                profile=config.profile,
                job_id=job_id,
                source_id=input_root.root_id,
            )
            processing_started_perf = time.perf_counter()
            process_job(run_dir)
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
                "job_id": job_id,
                "result_state": result_state,
                "updated_at": updated_at,
            }
            if result_state == "completed":
                state_entry["latest_success_run_dir"] = str(run_dir)
                state_entry["latest_success_job_id"] = job_id
                state_entry["latest_success_at"] = updated_at
            elif isinstance(previous, dict):
                for success_key in ("latest_success_run_dir", "latest_success_job_id", "latest_success_at"):
                    if previous.get(success_key):
                        state_entry[success_key] = previous[success_key]
            state_items[key] = state_entry
            item = {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "status": result_state,
                "run_dir": str(run_dir),
                "job_id": job_id,
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

        report_path = build_refresh_report_path(config.output_root, started_at)
        report = {
            "schema_version": 1,
            "started_at": started_at,
            "completed_at": completed_at,
            "config_path": str(config_path),
            "output_root": str(config.output_root),
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
        latest_path = config.output_root / "refresh-latest.md"
        report["latest_markdown_path"] = str(latest_path)
        index_json_path = config.output_root / "index.json"
        index_markdown_path = config.output_root / "index.md"
        report["index_json_path"] = str(index_json_path)
        report["index_markdown_path"] = str(index_markdown_path)
        write_json(report_path, report)
        write_refresh_latest_markdown(config.output_root, report)
        write_refresh_index(config.output_root, state, report)
        return report


def elapsed_seconds(started_perf: float) -> float:
    return round(time.perf_counter() - started_perf, 6)


def build_job_id(source_path: Path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    token = uuid.uuid4().hex[:8]
    return f"job-{stamp}-{slugify(source_path.stem)[:32]}-{token}"


def request_to_dict(request: JobRequest) -> dict[str, object]:
    return {
        "schema_version": request.schema_version,
        "job_id": request.job_id,
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
