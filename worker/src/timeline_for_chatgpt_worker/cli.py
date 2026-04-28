from __future__ import annotations

import argparse
from pathlib import Path
import time
import uuid

from .contracts import InputItem, JobRequest, JobStatus, ParserOptions
from .fs_utils import ensure_dir, now_iso, slugify, write_json
from .processor import outputs_root, process_job, process_pending_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TimelineForChatGPT worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    process = subparsers.add_parser("process", help="Create and run a job for one ChatGPT export.")
    process.add_argument("input_path", help="Path to a ChatGPT export ZIP or extracted export directory.")
    process.add_argument("--output-root", help="Directory where job output folders are written.")
    process.add_argument("--profile", default="timeline-default")
    process.add_argument("--job-id", help="Optional explicit job id. Defaults to a generated job id.")
    process.add_argument("--enqueue-only", action="store_true", help="Create request/status files without processing.")

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
                source_id="cli",
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
