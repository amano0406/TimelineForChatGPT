from __future__ import annotations

import argparse
from pathlib import Path
import time
import uuid

from .contracts import InputItem, JobRequest, JobStatus, ParserOptions
from .fs_utils import ensure_dir, load_json, now_iso, slugify, write_json
from .processor import outputs_root, process_job, process_pending_jobs
from .refresh import (
    build_refresh_job_id,
    build_refresh_report_path,
    default_config_path,
    discover_inputs,
    fingerprint_file,
    load_refresh_state,
    load_runtime_config,
    same_fingerprint,
    validate_runtime_config,
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
    refresh.add_argument("--config", default=str(default_config_path()), help="Runtime config JSON path.")
    refresh.add_argument("--dry-run", action="store_true", help="Write a refresh report without processing jobs.")
    refresh.add_argument("--force", action="store_true", help="Process every discovered input even when unchanged.")

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
            config_path=Path(args.config),
            dry_run=bool(args.dry_run),
            force=bool(args.force),
        )
        print(report["report_path"])
        return 0

    if args.command == "run-once":
        process_pending_jobs()
        return 0

    while True:
        process_pending_jobs()
        time.sleep(max(1, int(args.poll_interval)))


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
    config = load_runtime_config(config_path)
    warnings = validate_runtime_config(config)
    started_at = now_iso()
    ensure_dir(config.output_root)
    ensure_dir(config.state_root)
    state = load_refresh_state(config.state_root)
    state_items = state.setdefault("items", {})
    report_items: list[dict[str, object]] = []
    processed = 0
    skipped = 0
    failed = 0

    for input_root, input_path in discover_inputs(config):
        key = str(input_path)
        previous = state_items.get(key) if isinstance(state_items.get(key), dict) else {}
        fingerprint = fingerprint_file(input_path, previous)
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
            report_items.append(
                {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "skipped_unchanged",
                    "previous_run_dir": str(previous_run_dir),
                    "result_state": previous_state,
                    "fingerprint": fingerprint,
                }
            )
            continue

        job_id = build_refresh_job_id(input_root.root_id, input_path, fingerprint, started_at)
        if dry_run:
            skipped += 1
            report_items.append(
                {
                    "input_root_id": input_root.root_id,
                    "input_path": str(input_path),
                    "status": "would_process",
                    "job_id": job_id,
                    "fingerprint": fingerprint,
                }
            )
            continue

        run_dir = create_job_from_input(
            input_path=input_path,
            output_root=config.output_root,
            profile=config.profile,
            job_id=job_id,
            source_id=input_root.root_id,
        )
        process_job(run_dir)
        status_payload = load_json(run_dir / "status.json")
        result_payload = load_json(run_dir / "result.json")
        result_state = str(result_payload.get("state") or status_payload.get("state") or "unknown")
        if result_state == "completed":
            processed += 1
        else:
            failed += 1

        state_items[key] = {
            "input_root_id": input_root.root_id,
            "input_path": str(input_path),
            "display_name": input_path.name,
            "fingerprint": fingerprint,
            "run_dir": str(run_dir),
            "job_id": job_id,
            "result_state": result_state,
            "updated_at": now_iso(),
        }
        report_items.append(
            {
                "input_root_id": input_root.root_id,
                "input_path": str(input_path),
                "status": result_state,
                "run_dir": str(run_dir),
                "job_id": job_id,
                "fingerprint": fingerprint,
                "message": status_payload.get("message"),
            }
        )

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
            "discovered": len(report_items),
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
        },
        "items": report_items,
        "report_path": str(report_path),
    }
    latest_path = config.output_root / "refresh-latest.md"
    report["latest_markdown_path"] = str(latest_path)
    write_json(report_path, report)
    write_refresh_latest_markdown(config.output_root, report)
    return report


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
